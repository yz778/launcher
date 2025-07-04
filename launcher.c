#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <linux/limits.h>

// Function to get the socket path
const char* get_socket_path() {
    const char* app_name = "launcher";
    const char* runtime_dir = getenv("XDG_RUNTIME_DIR");
    static char socket_path[256];

    if (runtime_dir && strlen(runtime_dir) > 0) {
        snprintf(socket_path, sizeof(socket_path), "%s/%s.sock", runtime_dir, app_name);
    } else {
        // Fallback to /tmp if XDG_RUNTIME_DIR is not set
        const char* tmp_dir = "/tmp";
        snprintf(socket_path, sizeof(socket_path), "%s/%s.sock", tmp_dir, app_name);
    }
    return socket_path;
}

int main(int argc, char *argv[]) {
    // Try socket connection first
    int fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (fd != -1) {
        struct sockaddr_un addr = {.sun_family = AF_UNIX};
        strncpy(addr.sun_path, get_socket_path(), sizeof(addr.sun_path) - 1);
        addr.sun_path[sizeof(addr.sun_path) - 1] = '\0';

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
    char *args[argc + 3];
    char venv_python[PATH_MAX];
    snprintf(venv_python, sizeof(venv_python), "%s/../.venv/bin/python", path);

    args[0] = venv_python;
    args[1] = "-m";
    args[2] = "launcher.launcher";
    // Copy command-line arguments (argv[1] onwards) to the Python script's arguments (args[3] onwards).
    // The number of arguments to copy is argc - 1.
    int i;
    for (i = 0; i < argc - 1; ++i) {
        args[3 + i] = argv[1 + i];
    }
    args[3 + (argc - 1)] = NULL; // NULL-terminate the argument array for execvp

    // Try venv python first, fallback to system python
    execvp(venv_python, args);
    args[0] = "python";
    execvp("python", args);

    return 1;
}
