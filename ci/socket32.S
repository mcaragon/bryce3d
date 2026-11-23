# Minimal 32-bit x86 program: calls socket(AF_UNIX, SOCK_STREAM) and exits with
# 253 on success or the errno (38 = ENOSYS = blocked by seccomp/kernel).
# Used by CI to check whether the host lets 32-bit code (Wine) open sockets.
.globl _start
_start:
  movl $359, %eax      # socket(AF_UNIX=1, SOCK_STREAM=1, 0) via direct i386 syscall
  movl $1, %ebx
  movl $1, %ecx
  xorl %edx, %edx
  int $0x80
  negl %eax            # exit code = -ret (errno) if error, else small negative->big
  movl %eax, %ebx
  movl $1, %eax
  int $0x80
