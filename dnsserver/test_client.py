#!/usr/bin/python3

#   ./test_client          - No arguments, defaults to query of DEFAULT_QUERY
#   ./test_client asdf.com - queries "asdf.com" instead

TARGET_IP = "127.0.0.1"
TARGET_PORT = 53
DEFAULT_QUERY = "example.com"


import sys
import socket
import random
import time
import struct
from dnslib import *

def prepareMessage(msg):
   msg = bytes(msg, 'utf-8')
   #data = struct.pack(">H", len(msg)) + msg
   return(data)


if(len(sys.argv) != 2):
   query = DEFAULT_QUERY
else:
   query = sys.argv[1]

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.connect((TARGET_IP, TARGET_PORT))

d = DNSRecord.question(query, "A")

print(d)

s.send(d.pack())

m = s.recv(1024)

m = DNSRecord.parse(m)

print(m)
