#!/usr/bin/env python

import array
import datetime
import getopt
import numpy
import struct
import sys
import xml.etree.cElementTree as ET

''' Global '''
BIG_ENDIAN = False
EIT_SIZE = 10
VERBOSE = False

EPG_SHORT_DESC = 0x4d
EPG_LONG_DESC = 0x4e

EPG_LONG_DESC_ONCE = 0x00
EPG_LONG_DESC_START = 0x01
EPG_LONG_DESC_ADD = 0x11

''' Classes '''
class Description:
	def __init__(self, lang, short, bytes):
		self.lang = ""
		self.short = short
		self.text = ""

		for c in lang:
			if c != 0:
				self.lang = self.lang + "%c" % (c)
			else:
				break

		i = 0
		for c in bytes:
			if short and i == 0 and c == 0x15:
				continue
			elif c != 0:
				self.text = self.text + "%c" % (c)
			else:
				break
			i = i + 1

	def append(self, bytes):
		for c in bytes:
			if c != 0:
				self.text = self.text + "%c" % (c)
			else:
				break

	def __str__(self):
		return "%s: %s" % (self.lang, self.text)

class Descriptor:
	def __init__(self, id, refs, data):
		self.id = id
		self.refs = refs
		self.data = data

	def __str__(self):
		return "Desc: ID[%08x] Refs[%02d] Data[%s]" % (self.id, self.refs, array_to_str(self.data))

class EIT:
	def __init__(self, id, start, duration):
		self.id = id
		self.start = start
		self.duration = duration

	def __str__(self):
		return "EIT: ID[%d] start[%s] duration[%d]" % (self.id, self.start.strftime("%Y/%m/%d %H:%M"), self.duration)

class Event:
	def __init__(self, type, len):
		self.type = type
		self.len = len
		self.crcs = []
		self.eit = ""
		self.short_desc = ""
		self.long_desc = ""

	def add_crc(self, crc):
		self.crcs.append(crc)

	def add_desc(self, desc):
		if desc.data[0] == EPG_SHORT_DESC:
			self.short_desc = Description(desc.data[2:5], True, desc.data[7:])
		elif desc.data[0] == EPG_LONG_DESC:
			if desc.data[2] == EPG_LONG_DESC_ONCE:
				self.long_desc = Description(desc.data[3:6], False, desc.data[8:])
			elif desc.data[2] == EPG_LONG_DESC_START:
				self.long_desc = Description(desc.data[3:6], False, desc.data[9:])
			elif desc.data[2] == EPG_LONG_DESC_ADD:
				self.long_desc = self.long_desc.append(desc.data[8:])
			else:
				print "ERROR: unsupported long desc type 0x%02x -> %s" % (desc.data[2], array_to_str(desc.data))
		else:
			print "ERROR: unsupported desc type 0x%02x -> %s" % (desc.data[0], array_to_str(desc.data))

	def desc(self):
		if self.long_desc:
			return unicode(self.long_desc.text, "utf-8", "ignore")
		else:
			return None

	def date(self):
		return self.eit.start.strftime("%Y%m%d")

	def start(self):
		return self.eit.start.strftime("%Y%m%d%H%M%S +0100")

	def stop(self):
		return (self.eit.start + datetime.timedelta(seconds=self.eit.duration)).strftime("%Y%m%d%H%M%S +0100")

	def title(self):
		if self.short_desc:
			return unicode(self.short_desc.text, "utf-8", "ignore")
		else:
			return None

	def __str__(self):
		return "%s\n\t%s\n\t%s" % (self.eit, self.short_desc, self.long_desc)

class Channel:
	def __init__(self, sid, nid, tsid):
		self.sid = sid
		self.nid = nid
		self.tsid = tsid
		self.events = []

	def add_event(self, event):
		self.events.append(event)

	def id(self):
		return "%X:%X:%X" % (self.sid, self.nid, self.tsid)

	def __str__(self):
		res = "Channel: SID[%d] NID[%d] TSID[%d]" % (self.sid, self.nid, self.tsid)
		evt = 0
		for event in self.events:
			res = res + "\n" + str(event)
		res += "\n"
		return res

''' Helper functions '''
def indent(elem, level=0):
	i = "\n" + level*"\t"
	if len(elem):
		if not elem.text or not elem.text.strip():
			elem.text = i + "\t"
		if not elem.tail or not elem.tail.strip():
			elem.tail = i
		for elem in elem:
			indent(elem, level+1)
		if not elem.tail or not elem.tail.strip():
			elem.tail = i
	else:
		if level and (not elem.tail or not elem.tail.strip()):
			elem.tail = i

def array_to_str(arr):
	str = ""
	for c in arr:
		str = str + " " + "%02x" % (c)
	return str[1:]

def bcd_to_int(x):
	if x < 0:
		raise ValueError("Cannot be a negative integer")

	if x == 0:
		return 0

	bcdstring = ''
	while x > 0:
		nibble = x % 16
		bcdstring = str(nibble) + bcdstring
		x >>= 4

	return int(bcdstring)

def read_str(fd, str_len):
	return fd.read(str_len)

def read_i8(fd):
	return struct.unpack('b', fd.read(1))[0]

def read_i16(fd):
	global BIG_ENDIAN

	if BIG_ENDIAN:
		return struct.unpack('>h', fd.read(2))[0]
	else:
		return struct.unpack('<h', fd.read(2))[0]

def read_i32(fd):
	global BIG_ENDIAN

	if BIG_ENDIAN:
		return struct.unpack('>i', fd.read(4))[0]
	else:
		return struct.unpack('<i', fd.read(4))[0]

def read_u8(fd):
	return struct.unpack('B', fd.read(1))[0]

def read_u16(fd):
	global BIG_ENDIAN

	if BIG_ENDIAN:
		return struct.unpack('>H', fd.read(2))[0]
	else:
		return struct.unpack('<H', fd.read(2))[0]

def read_u32(fd):
	global BIG_ENDIAN

	if BIG_ENDIAN:
		return struct.unpack('>I', fd.read(4))[0]
	else:
		return struct.unpack('<I', fd.read(4))[0]

''' Functions '''
def eit_event_id(eit_data):
	return struct.unpack('!H', eit_data[0:2])[0]

def eit_event_start(eit_data):
	mjd = struct.unpack('!H', eit_data[2:4])[0]

	year = int((mjd - 15078.2) / 365.25)
	month = int(((mjd - 14956.1) - int(year * 365.25)) / 30.6001)
	day = mjd - 14956 - int(year * 365.25) - int(month * 30.6001)
	if month == 14 or month == 15:
		k = 1
	else:
		k = 0

	year = year + k + 1900
	month = month - 1 - k * 12

	hour = bcd_to_int(struct.unpack('B', eit_data[4:5])[0])
	minute = bcd_to_int(struct.unpack('B', eit_data[5:6])[0])

	return datetime.datetime(year, month, day, hour, minute)

def eit_event_duration(eit_data):
	hours = struct.unpack('B', eit_data[7:8])[0]
	minutes = struct.unpack('B', eit_data[8:9])[0]
	seconds = struct.unpack('B', eit_data[9:10])[0]

	return bcd_to_int(hours) * 3600 + bcd_to_int(minutes) * 60 + bcd_to_int(seconds)

def epg_parse_event(epg):
	type = read_u8(epg)
	len = read_u8(epg)
	eit_data = read_str(epg, EIT_SIZE)
	num_crc = (len - EIT_SIZE) / 4

	event = Event(type, len)
	event.eit = EIT(eit_event_id(eit_data), eit_event_start(eit_data), eit_event_duration(eit_data))

	crc = 0
	while crc < num_crc:
		event.add_crc(read_u32(epg))
		crc = crc + 1

	return event

def epg_parse_channel(epg):
	sid = read_i32(epg)
	nid = read_i32(epg)
	tsid = read_i32(epg)
	num_evt = read_i32(epg)

	channel = Channel(sid, nid, tsid)

	evt = 0
	while evt < num_evt:
		channel.add_event(epg_parse_event(epg))
		evt += 1

	return channel

def epg_parse_desc(epg):
	id = read_u32(epg)
	ref_cnt = read_i32(epg)

	data = []
	data.append(read_u8(epg))
	data.append(read_u8(epg))

	idx = 0
	while idx < data[1]:
		data.append(read_u8(epg))
		idx = idx + 1

	descriptor = Descriptor(id, ref_cnt, data)

	return descriptor

def channels_to_xmltv(epg_xml, channels):
	tv_params = dict()
	tv_params['generator-info-name'] = "enigma2-epg"
	tv = ET.Element("tv", tv_params)

	for chn in channels:
		chan_params = dict()
		chan_params['id'] = chn.id()
		chan = ET.SubElement(tv, "channel", chan_params)
		for evt in chn.events:
			prog_params = dict()
			prog_params['start'] = evt.start()
			prog_params['stop'] = evt.stop()
			prog_params['channel'] = chn.id()
			prog = ET.SubElement(tv, "programme", prog_params)
			if evt.title():
				title = ET.SubElement(prog, "title")
				title.text = evt.title()
			if evt.desc():
				desc = ET.SubElement(prog, "desc")
				desc.text = evt.desc()
			date = ET.SubElement(prog, "date")
			date.text = evt.date()

	tree = ET.ElementTree(tv)
	indent(tv)
	tree.write(epg_xml, encoding="utf-8", xml_declaration=True)

def epg_dat_parse(epg_dat, epg_xml):
	global BIG_ENDIAN, VERBOSE

	channels = []
	descriptors = dict()
	epg = open(epg_dat, "r")

	magic = read_u32(epg)
	header = read_str(epg, 13)

	print "Magic 0x%x" % magic
	print "Header: %s" % header

	if magic == 0x32547698:
		BIG_ENDIAN = True
		print "Big Endian format detected"
	elif magic != 0x98765432:
		sys.exit(3)

	if header != "ENIGMA_EPG_V7":
		sys.exit(4)

	num_chn = read_i32(epg)

	print "EPG channels: %d" % (num_chn)

	chn = 0
	while chn < num_chn:
		channels.append(epg_parse_channel(epg))
		chn += 1

	num_desc = read_i32(epg)
	desc = 0
	while desc < num_desc:
		new_desc = epg_parse_desc(epg)
		descriptors[str(new_desc.id)] = new_desc
		desc = desc + 1

	for chn in channels:
		for evt in chn.events:
			for crc in evt.crcs:
				if str(crc) in descriptors:
					evt.add_desc(descriptors[str(crc)])

	channels_to_xmltv(epg_xml, channels)

	if VERBOSE:
		print ""
		for chn in channels:
			print chn

	epg.close()

def main(argv):
	global BIG_ENDIAN, VERBOSE
	epg_dat = ""
	epg_xml	= ""

	try:
		opts, args = getopt.getopt(argv[1:], "bhi:o:v", ["big-endian", "help", "input=", "output="])
	except getopt.GetoptError as err:
		print str(err)
		sys.exit(2)
	for opt, arg in opts:
		if opt in ("-b", "--big-endian"):
			BIG_ENDIAN = True
		elif opt in ("-h", "--help"):
			sys.exit()
		elif opt in ("-i", "--input"):
			epg_dat=arg
		elif opt in ("-o", "--output"):
			epg_xml=arg
		elif opt == "-v":
			VERBOSE = True

	epg_dat_parse(epg_dat, epg_xml)

if __name__ == "__main__":
	main(sys.argv)
