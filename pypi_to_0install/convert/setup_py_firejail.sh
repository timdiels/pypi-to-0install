#!/bin/sh
# Try generate egg-info in sandbox
set -o errexit -o nounset

output_directory="$1"
firejail_profile_file="$2"
python="$3"
shift 3

for tasks_file in "$@"
do
    echo $$ > $tasks_file
done

firejail \
    --shell=/bin/sh \
    --private="$output_directory" \
    --profile="$firejail_profile_file" \
    -- sh -c \
    "export TMPDIR=$HOME/tmp && cd dist && $python setup.py egg_info --egg-base ../out"
