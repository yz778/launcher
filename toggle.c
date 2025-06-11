#include <stdio.h>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <string.h>
#include <linux/limits.h>

int main(int argc, char *argv[]) {
    // Try socket connection first
    int fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (fd != -1) {
        struct sockaddr_un addr = {.sun_family = AF_UNIX};
        strcpy(addr.sun_path, "/tmp/launcher.sock");

        struct timeval timeout = {0, 50000};
        setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));

        if (connect(fd, (struct sockaddr*)&addr, sizeof(addr)) == 0) {
            write(fd, "SHOW", 4);
            char buf;
            if (read(fd, &buf, 1) >= 0) {
                close(fd);
                return 0;
            }
        }
        close(fd);
    }

    // Get executable directory
    char path[PATH_MAX];
    ssize_t len = readlink("/proc/self/exe", path, sizeof(path) - 1);
    if (len == -1) return 1;
    path[len] = '\0';

    char *last_slash = strrchr(path, '/');
    if (!last_slash) return 1;
    *last_slash = '\0';

    if (chdir(path) != 0) return 1;

    // Build argument array
    char *args[argc + 2];
    char venv_python[PATH_MAX];
    snprintf(venv_python, sizeof(venv_python), "%s/.venv/bin/python", path);

    args[0] = venv_python;
    args[1] = "main.py";
    memcpy(&args[2], &argv[1], argc * sizeof(char*));

    // Try venv python first, fallback to system python
    execvp(venv_python, args);
    args[0] = "python";
    execvp("python", args);

    return 1;
}