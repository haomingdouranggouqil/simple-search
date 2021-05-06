CC = gcc
CFLAGS = -Wall -std=c99 -D_GNU_SOURCE -D_FILE_OFFSET_BITS=64 -O3 -g -I ./include
OBJS = ss.o util.o token.o search.o postings.o database.o poemload.o
DATE=$(shell date "+%Y%m%d")
DIR_NAME=ss-${DATE}

ss: $(OBJS)
	$(CC) $(CFLAGS) -o $@ $(OBJS) -l sqlite3 -l expat -l m

.c.o:
	$(CC) $(CFLAGS) -c $<

ss.o: ss.h util.h token.h search.h postings.h database.h poemload.h
util.o: util.h
token.o: ss.h token.h
search.o: ss.h util.h token.h search.h postings.h
postings.o: ss.h util.h postings.h database.h
database.o: ss.h util.h database.h
poem.o: ss.h poemload.h

.PHONY: clean
clean:
	rm *.o

dist:
	rm -rf $(DIR_NAME)
	mkdir $(DIR_NAME)
	cp -R *.c *.h include Makefile README $(DIR_NAME)
	tar cvfz $(DIR_NAME).tar.gz $(DIR_NAME)
	rm -rf $(DIR_NAME)
