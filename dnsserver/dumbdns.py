#!/usr/bin/python3

#Customised dns server for python 3.2+ using dnslib
#Should be run as a daemon, either with the supplied daemon manager, or through
#initscripts/systemd
#
# Reference implementation of this simple dns server and accompanying daemoniser here:
#    https://gist.github.com/wmax641/aa50e3bb924e138d94e9
#
# Based off this:
#     https://gist.github.com/andreif/6069838
#
#

##### Settings (change these): #####
WORKER_USERNAME="nobody"  #Unprivileged user and group to run the worker thread
WORKER_GROUP="nobody"
LISTENING_PORT = 53     #Port to listen on
UDP_LISTEN = True       #Listen on UDP?
TCP_LISTEN = False      #Listen on TCP as well?
ALSO_LOG_STDOUT = True  #Print to stdout as well as logging
LOG_LOCATION = "/var/log/dumbdns-server.log"
MAX_LOG_SIZE = 20000
LOG_ROTATIONS = 1
LOG_HANDLE = "dumbdns-server"

#Location for PID file (Not set here anymore)
#PID file location set in either an init-script, or the provided daemoniser if you 
#choose to use it (dumb-dns-daemon.py)
#PID_FILE = "/var/run/dumbdns.pid" 

# Dns info to serve
domain = 'example.com.' #Fully Qualified Domain Name, in LOWER CASE.
IP = "1.2.3.4"
TTL = 300

import logging
import logging.handlers
import os
import sys
import time
import argparse
import datetime
import threading
import traceback
import socketserver
import struct
import pwd
try:
    from dnslib import *
except ImportError:
    print("Missing dependency dnslib. Please install it with `pip`.")
    sys.exit(2)

class DomainName(str):
    def __getattr__(self, item):
        return DomainName(item + '.' + self)

D = DomainName(domain)

soa_record = SOA(
    mname=D.ns1,  # primary name server
    rname=D.spam,  # email of the domain administrator
    times=(
        201506013,  # serial number
        7200,  # refresh 7200
        10800,  # retry  10800
        259200,  # expire 259200
        7200,  # minimum 3600
    )
)

ns_records = [NS(D.ns1), NS(D.ns2)]
records = {
    D: [A(IP), AAAA((0,) * 16), MX(D.mail), soa_record] + ns_records,
    D.ns1: [A(IP)],  
    D.ns2: [A(IP)],
}

def dns_response(request):

   qname = request.q.qname
   qn = str(qname)
   qtype = request.q.qtype
   qt = QTYPE[qtype]
     
   #If relevant query domain do... Otherwise return(None)
   if qn.lower() == D or qn.lower().endswith('.' + D):
      reply = DNSRecord(DNSHeader(id=request.header.id, qr=1, aa=1, ra=1), q=request.q)

      #if query type is "A" or type 1, reply with answer ipaddr of IP
      if(qtype == 1):
         reply.add_answer(RR(rname=qname, rtype=1, rclass=1, ttl=TTL, rdata=A(IP)))

      #otherwise if query is type "AAAA" or type 28, ignore ipv6
      elif(qtype == 28):
         reply.header.set_rcode(3) #RCODE = 3 is "NXDomain"
      
      #otherwise, give generic response
      else:
         for name, rrs in records.items():
            if name == qn:
               for rdata in rrs:
                  rqt = rdata.__class__.__name__
                  if qt in ['*', rqt]:
                     reply.add_answer(RR(rname=qname, rtype=getattr(QTYPE, rqt), rclass=1, ttl=TTL, rdata=rdata))

         for rdata in ns_records:
            reply.add_ar(RR(rname=D, rtype=QTYPE.NS, rclass=1, ttl=TTL, rdata=rdata))

         reply.add_auth(RR(rname=D, rtype=QTYPE.SOA, rclass=1, ttl=TTL, rdata=soa_record))

      return(reply) 

   else:
      #invalid domain, not our problem. Ignore...
      return(None)

      #Or you could be more polite and return something like this:
      #reply.header.set_rcode(3) #RCODE = 3 is "NXDomain"
      #return(reply)

class BaseRequestHandler(socketserver.BaseRequestHandler):

   log = logging.getLogger(LOG_HANDLE)

   def get_data(self):
      raise NotImplementedError

   def send_data(self, data):
      raise NotImplementedError

   def handle(self):
      now = datetime.datetime.now().strftime("%a %d-%b %H:%M:%S")
      self.log.info("{}: request from ({}:{})".format(now, self.client_address[0], self.client_address[1]))
      try:
         data = self.get_data()
         request = DNSRecord.parse(data)
         try:
            #Change this to make the logging more or less verbose
            self.log.info("\t|-> qtype={}, qname={}".format(request.q.qtype, request.q.qname))
         except:
            pass
         data = dns_response(request)
         if(data is not None):
            #Change this to make the logging more or less verbose
            #self.log.info("---- Reply:----\n{}\n".format(data))
            self.send_data(data.pack())
            self.log.info("\t|-> Sent reply")
            pass
         else:
            self.log.info("\t|-> Ignoring invalid domain...")
            pass

      except Exception:
         self.log.info("\t|-> Ignoring bad packet (caused exception)")

class TCPRequestHandler(BaseRequestHandler):
   
   def get_data(self):
      data = self.request.recv(8192).strip()
      sz = struct.unpack('>H', data[:2])[0]
      if sz < len(data) - 2:
         raise Exception("Wrong size of TCP packet")
      elif sz > len(data) - 2:
         raise Exception("Too big TCP packet")
      return data[2:]

   def send_data(self, data):
      sz = struct.pack('>H', len(data))
      return self.request.sendall(sz + data)

class UDPRequestHandler(BaseRequestHandler):

   def get_data(self):
      return self.request[0].strip()

   def send_data(self, data):
      return self.request[1].sendto(data, self.client_address)


def startServer():

   servers = []
   if UDP_LISTEN: servers.append(socketserver.ThreadingUDPServer(('', LISTENING_PORT), UDPRequestHandler))
   if TCP_LISTEN: servers.append(socketserver.ThreadingTCPServer(('', LISTENING_PORT), TCPRequestHandler))

   log = logging.getLogger(LOG_HANDLE)
   log.setLevel(logging.INFO)
   log_handler = logging.handlers.RotatingFileHandler(LOG_LOCATION, maxBytes=MAX_LOG_SIZE, backupCount=LOG_ROTATIONS)
   log.addHandler(log_handler)
   if(ALSO_LOG_STDOUT):
      log_handler_stdout = logging.StreamHandler(sys.stdout)
      log.addHandler(log_handler_stdout)
   
   now = datetime.datetime.now().strftime("%a %d-%b %H:%M:%S")
   log.info("{}: Starting nameserver on port {}\n".format(now, LISTENING_PORT))
   
   #drop privileges (Should be started as root first to bind to port 53)
   try:
      os.setgid(int(pwd.getpwnam(WORKER_GROUP).pw_gid))
      os.setuid(int(pwd.getpwnam(WORKER_USERNAME).pw_uid))
   except:
      sys.exit(2)

   for s in servers:
      thread = threading.Thread(target=s.serve_forever)  
      thread.daemon = True  # exit the server thread when the main thread terminates
      thread.start()

   try:
      while True:
         time.sleep(1)
   except KeyboardInterrupt:
      pass
   finally:
      for s in servers:
         s.shutdown()
         
if __name__ == '__main__':
   startServer()
