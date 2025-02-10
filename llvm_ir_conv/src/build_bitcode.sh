./Configure linux-x86_64-clang

bear -n -o compile_db.json sh -c 'make clean && make build_libs -j8'

python3 ./comp_db_generate.py -o ./build.sh -l $LLVM_PROJECT_PATH/build compile_db.json generate

/bin/bash ./build.sh

mkdir ./bcs

find . -type f -name "*.bc" -exec mv {} ./bcs  \;