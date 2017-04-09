#!/bin/sh
# Try generate egg-info in sandbox
set -o errexit -o nounset

output_directory="$1"
firejail_profile_file="$2"
python="$3"
setup="$4"
shift 4

for tasks_file in "$@"
do
    echo $$ > $tasks_file
done

firejail \
    --shell=/bin/sh \
    --private="$output_directory" \
    --profile="$firejail_profile_file" \
    -- sh -c \
    "cd dist && TMPDIR=$HOME/tmp PYTHONPATH=`dirname $setup` $python $setup egg_info --egg-base ../out ; true"
