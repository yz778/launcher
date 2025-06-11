#include <stdio.h>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <string.h>
#include <linux/limits.h>

int main(int argc, char *argv[]) {
    const char *socket_path = "/tmp/launcher.sock";
    struct sockaddr_un addr;
    int fd;

    // Try to connect to socket
    if ((fd = socket(AF_UNIX, SOCK_STREAM, 0)) != -1) {
        memset(&addr, 0, sizeof(addr));
        addr.sun_family = AF_UNIX;
        strncpy(addr.sun_path, socket_path, sizeof(addr.sun_path) - 1);

        struct timeval timeout = {0, 50000}; // 50ms timeout
        setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));

        if (connect(fd, (struct sockaddr*)&addr, sizeof(addr)) == 0) {
            write(fd, "SHOW", 4);
            char buf[1];
            if (read(fd, buf, 1) >= 0) {
                close(fd);
                return 0; // Success, exit
            }
        }
        close(fd);
    }

    // Get launcher directory
    char path[PATH_MAX];
    ssize_t len = readlink("/proc/self/exe", path, PATH_MAX - 1);
    if (len == -1) return 1;
    path[len] = '\0';

    // Simple dirname: find last '/' and truncate
    char *last_slash = strrchr(path, '/');
    if (!last_slash) return 1;
    *last_slash = '\0';

    // Change to launcher directory
    if (chdir(path) != 0) return 1;

    // Prepare paths
    char launcher_path[PATH_MAX];
    char venv_python[PATH_MAX];
    snprintf(launcher_path, PATH_MAX, "%s/main.py", path);
    snprintf(venv_python, PATH_MAX, "%s/.venv/bin/python", path);

    // Prepare arguments
    char *args[argc + 2];
    args[0] = venv_python;
    args[1] = launcher_path;
    for (int i = 1; i < argc; i++) args[i + 1] = argv[i];
    args[argc + 1] = NULL;

    // Try venv Python
    execvp(venv_python, args);

    // Fallback to system Python
    args[0] = "python";
    execvp("python", args);
    return 1; // execvp only returns on error
}
