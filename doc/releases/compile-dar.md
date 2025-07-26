## build

This worked for dar version 2.7.18 on ubuntu 24.04 as delivered from `multipass`


```bash
sudo apt update && sudo apt upgrade -y 
sudo apt install -y binutils-for-build pkg-config gcc g++ make autoconf automake libtool bzip2 \
  libkrb5-dev pkg-config zlib1g-dev libbz2-dev liblzo2-dev liblzma-dev libzstd-dev \
  liblz4-dev libgcrypt-dev libgpgme-dev doxygen graphviz upx groff  libext2fs-dev \
  libthreadar-dev librsync-dev  libcurl4-gnutls-dev libargon2-dev 
```

```bash
TAR_FILE=~/dar-2.7.18.tar.gz
export SRC_CODE=/tmp/dar-2.7.18
export DAR_DIR=/usr/local
tar zxvf "$TAR_FILE"  --directory=/tmp 
```

```bash
cd "$SRC_CODE"
CXXFLAGS=-O
export CXXFLAGS
make clean distclean
./configure --prefix="$DAR_DIR" LDFLAGS="-lgssapi_krb5" --disable-python-binding
make
sudo make install-strip
echo "/usr/local/lib" | sudo tee /etc/ld.so.conf.d/local.conf
/usr/local/bin/dar --version
```

gives

```bash
dar and libdar have been successfully configured with the following parameters:

  LIBDAR parameters:
   Zlib compression (gzip)    : YES
   Libbz2 compression (bzip2) : YES
   Liblzo2 compression (lzo)  : YES
   Liblxz compression (xz)    : YES
   Liblzstd compression (zstd): YES
   Liblz4 compression (lz4)   : YES
   Strong encryption support  : YES
   Public key cipher support  : YES
   Extended Attributes support: YES
   Large files support (> 2GB): YES
   extX FSA / nodump support  : YES
   HFS+ FSA support           : NO
   statx() support            : YES
   Integer size used          : 64
   Thread safe support        : YES
   Furtive read mode          : YES
   Large directory optim.     : YES
   posix fadvise support      : YES
   timepstamps write accuracy : 1 nanosecond
   timestamps read accuracy   : 1 nanosecond
   can restore symlink dates  : YES
   can uses multiple threads  : YES
   Delta-compression support  : YES
   Remote repository support  : YES
   Argon2 hashing algorithm   : YES

  DAR SUITE command line programs:
   Long options available : YES
   Building examples      : NO
   Building dar_static    : YES
   using upx at install   : YES
   building documentation : YES
   building python binding: NO
```

```bash
make
make install-strip
 ~/.local/dar-2.7.18/bin/dar --version


 dar version 2.7.18, Copyright (C) 2002-2025 Denis Corbin
   Long options support         : YES

 Using libdar 6.8.2 built with compilation time options:
   gzip compression (libz)      : YES
   bzip2 compression (libbzip2) : YES
   lzo compression (liblzo2)    : YES
   xz compression (liblzma)     : YES
   zstd compression (libzstd)   : YES
   lz4 compression (liblz4)     : YES
   Strong encryption (libgcrypt): YES
   Public key ciphers (gpgme)   : YES
   Extended Attributes support  : YES
   Large files support (> 2GB)  : YES
   ext2fs NODUMP flag support   : YES
   Integer size used            : 64 bits
   Thread safe support          : YES
   Furtive read mode support    : YES
   Linux ext2/3/4 FSA support   : YES
   Mac OS X HFS+ FSA support    : NO
   Linux statx() support        : YES
   Detected system/CPU endian   : little
   Posix fadvise support        : YES
   Large dir. speed optimi.     : YES
   Timestamp read accuracy      : 1 nanosecond
   Timestamp write accuracy     : 1 nanosecond
   Restores dates of symlinks   : YES
   Multiple threads (libthreads): YES (1.4.0 - barrier using pthread_barrier_t)
   Delta compression (librsync) : YES
   Remote repository (libcurl)  : YES (libcurl/8.5.0 GnuTLS/3.8.3 zlib/1.3 brotli/1.1.0 zstd/1.5.5 libidn2/2.3.7 libpsl/0.21.2 (+libidn2/2.3.7) libssh/0.10.6/openssl/zlib nghttp2/1.59.0 librtmp/2.3 OpenLDAP/2.6.7)
   argon2 hashing (libargon2)   : YES

 compiled the Jul 26 2025 with GNUC version 13.3.0
 dar is part of the Disk ARchive suite (Release 2.7.18)
 dar comes with ABSOLUTELY NO WARRANTY; for details
 type `dar -W'. This is free software, and you are welcome
 to redistribute it under certain conditions; type `dar -L | more'
 for details.
```

```` bash
# I probably miss some libraries here, as they  were already installed
sudo apt-get install libkrb5-dev 
sudo apt-get install libgcrypt-dev libgpgme-dev libext2fs-dev  libthreadar-dev  librsync-dev  libcurl4-gnutls-dev
cd "$SRC_CODE"
CXXFLAGS=-O
export CXXFLAGS
make clean distclean
./configure --prefix="$DAR_DIR" LDFLAGS="-lgssapi_krb5"
make
make install-strip
````

This gives:

```` code
$HOME/.local/dar/bin/ --version

 dar version 2.7.17, Copyright (C) 2002-2025 Denis Corbin
   Long options support         : YES

 Using libdar 6.8.1 built with compilation time options:
   gzip compression (libz)      : YES
   bzip2 compression (libbzip2) : YES
   lzo compression (liblzo2)    : NO
   xz compression (liblzma)     : YES
   zstd compression (libzstd)   : YES
   lz4 compression (liblz4)     : NO
   Strong encryption (libgcrypt): YES
   Public key ciphers (gpgme)   : YES
   Extended Attributes support  : YES
   Large files support (> 2GB)  : YES
   ext2fs NODUMP flag support   : YES
   Integer size used            : 64 bits
   Thread safe support          : YES
   Furtive read mode support    : YES
   Linux ext2/3/4 FSA support   : YES
   Mac OS X HFS+ FSA support    : NO
   Linux statx() support        : YES
   Detected system/CPU endian   : little
   Posix fadvise support        : YES
   Large dir. speed optimi.     : YES
   Timestamp read accuracy      : 1 nanosecond
   Timestamp write accuracy     : 1 nanosecond
   Restores dates of symlinks   : YES
   Multiple threads (libthreads): YES (1.4.0 - barrier using pthread_barrier_t)
   Delta compression (librsync) : YES
   Remote repository (libcurl)  : YES (libcurl/8.5.0 GnuTLS/3.8.3 zlib/1.3 brotli/1.1.0 zstd/1.5.5 libidn2/2.3.7 libpsl/0.21.2 (+libidn2/2.3.7) libssh/0.10.6/openssl/zlib nghttp2/1.59.0 librtmp/2.3 OpenLDAP/2.6.7)
   argon2 hashing (libargon2)   : NO

 compiled the Mar 25 2025 with GNUC version 13.3.0
 dar is part of the Disk ARchive suite (Release 2.7.17)
 dar comes with ABSOLUTELY NO WARRANTY; for details
 type `dar -W'. This is free software, and you are welcome
 to redistribute it under certain conditions; type `dar -L | more'
 for details.
````
