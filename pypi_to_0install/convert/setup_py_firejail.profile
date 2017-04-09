# Firejail profile of: python setup_py egg-info
quiet

# no internet access
net none
protocol unix

# unprivileged
caps.drop all

# use default blacklist of syscalls
seccomp

# cannot increase privilege with e.g. suid binary
nonewprivs

# no root user
noroot

# no supplementary user groups
nogroups

nosound

# limit number of processes it may create
rlimit-nproc 10000

# blacklist files
noblacklist /bin
noblacklist /sbin
noblacklist /usr
noblacklist /lib*
noblacklist /proc
noblacklist /run
noblacklist /sys
noblacklist /home
noblacklist /dev
blacklist /*
blacklist /tmp/.X11-unix
blacklist /run/user/*/bus

# and make them read-only (does not affect private-*)
read-only /*

# Replace some directories with fake temporary ones
# /dev
private-dev

# Home is assumed to be replaced by CLI arg: --private=$some_dir

