#!/bin/sh

set -e

if [ -z "$1" ]; then
    echo "Usage: <package> [<architecture>]"
    echo "If architecture is a known Debian architecture, build"
    echo "a binary-only package for this architecture."
    echo "e.g. armhf or arm64"
    exit 1
fi

CURRENTDIR=`pwd`
NAME=${1}

if [ -x ./version.py ]; then
  VERSION=`python ./version.py`
else
  VERSION=`python setup.py --version`
fi

if [ -d ./dist/ ]; then
    rm -f ./dist/*
fi

python setup.py sdist

if [ -d .git ]; then
  LOG=`git log -n1 --pretty=format:"Last change %h by %an, %ar. %s%n" --no-merges`
fi

DIR=`mktemp -d`
if [ -f ./dist/${NAME}-${VERSION}.tar.gz ]; then
  mv -v ./dist/${NAME}-${VERSION}.tar.gz ${DIR}/${NAME}_${VERSION}.orig.tar.gz
else
  echo "WARNING: broken setuptools tarball - Debian bug #786977"
  mv -v ./dist/${NAME}*.tar.gz ${DIR}/${NAME}_${VERSION}.orig.tar.gz
fi
cd ${DIR}

# git clone https://github.com/Linaro/pkg-${NAME}.git

tar -xzf ${NAME}_${VERSION}.orig.tar.gz
if [ ! -d ${DIR}/${NAME}-${VERSION} ]; then
  mv -v ${DIR}/${NAME}-* ${DIR}/${NAME}-${VERSION}
fi

echo "debian: ${CURRENTDIR}/../debian"
if [ -d ${CURRENTDIR}/../debian ]; then
  cp -r -v ${CURRENTDIR}/../debian ${DIR}/${NAME}-${VERSION}
else
  echo "WARNING: no debian directory found"
  exit 1
fi

cd ${DIR}/${NAME}-${VERSION}

# dpkg-checkbuilddeps || mk-build-deps
# dpkg-checkbuilddeps
dpkg-checkbuilddeps
dch -v ${VERSION}-1 -D unstable "Local developer build"
if [ -n ${LOG} ]; then
  dch -a ${LOG}
fi
debuild -sa -uc -us
cd ${DIR}
rm -rf ${DIR}/${NAME}-${VERSION}
echo
echo ${LOG}
echo
echo "Use zless /usr/share/doc/${NAME}/changelog.Debian.gz"
echo "to view the changelog, once packages are installed."
echo
if [ -x /usr/bin/dcmd ]; then
    dcmd ls ${DIR}/${NAME}_${VERSION}*.changes
else
    echo ${DIR}
    ls ${DIR}
fi
