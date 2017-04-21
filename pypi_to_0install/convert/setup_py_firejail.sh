#!/bin/sh
# Try generate egg-info in sandbox
set -o errexit -o nounset

distribution_dir="$1"
firejail_profile_file="$2"
python="$3"
setup="$4"
shift 4

root_dir=`dirname $distribution_dir`
distribution=`basename $distribution_dir`
distribution="$HOME/$distribution"

for tasks_file in "$@"
do
    echo $$ > $tasks_file
done

firejail \
    --shell=/bin/sh \
    --private="$root_dir" \
    --profile="$firejail_profile_file" \
    -- sh -c \
    "cd $distribution && TMPDIR=$distribution.tmp PYTHONPATH=`$distribution` $python $setup egg_info --egg-base $distribution.out ; true"
