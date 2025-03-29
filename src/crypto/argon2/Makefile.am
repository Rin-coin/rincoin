noinst_LIBRARIES = libargon2.a

libargon2_a_SOURCES = \
    core.c \
    blake2/blake2b.c \
    encoding.c \
    argon2.c \
    ref.c \
    thread.c

AM_CFLAGS = -O2 -fPIC
AM_CPPFLAGS = -I$(srcdir)/include -I$(srcdir)/blake2
