# Base: docker-default AppArmor profile from moby v28.3.3
# Source: https://github.com/moby/moby/blob/v28.3.3/profiles/apparmor/default.c
# Deltas from docker-default:
#   - abi <abi/4.0> for userns mediation
#   - allow userns, mount, pivot_root for bubblewrap namespace setup
#   - every docker-default deny line retained

abi <abi/4.0>,
#include <tunables/global>

profile ergane-engine flags=(attach_disconnected,mediate_deleted) {
  #include <abstractions/base>

  network,
  capability,
  file,
  umount,

  # Deltas from docker-default: bwrap's namespace setup
  userns,
  mount,
  pivot_root,

  signal (receive) peer=unconfined,
  signal (receive) peer=runc,
  signal (receive) peer=crun,
  signal (send,receive) peer=ergane-engine,

  deny @{PROC}/* w,
  deny @{PROC}/{[^1-9],[^1-9][^0-9],[^1-9s][^0-9y][^0-9s],[^1-9][^0-9][^0-9][^0-9/]*}/** w,
  deny @{PROC}/sys/[^k]** w,
  deny @{PROC}/sys/kernel/{?,??,[^s][^h][^m]**} w,
  deny @{PROC}/sysrq-trigger rwklx,
  deny @{PROC}/kcore rwklx,

  deny /sys/[^f]*/** wklx,
  deny /sys/f[^s]*/** wklx,
  deny /sys/fs/[^c]*/** wklx,
  deny /sys/fs/c[^g]*/** wklx,
  deny /sys/fs/cg[^r]*/** wklx,
  deny /sys/firmware/** rwklx,
  deny /sys/devices/virtual/powercap/** rwklx,
  deny /sys/kernel/security/** rwklx,

  ptrace (trace,read,tracedby,readby) peer=ergane-engine,
}
