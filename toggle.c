#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <string.h>
#include <libgen.h>
#include <linux/limits.h>

// Get launcher directory by resolving the executable path
char* get_launcher_dir() {
    static char path[PATH_MAX];
    if (readlink("/proc/self/exe", path, PATH_MAX) == -1) {
        return NULL;
    }
    return dirname(path);
}

// Get Python executable (venv or system)
char* get_python_executable(const char* launcher_dir) {
    static char venv_python[PATH_MAX];
    snprintf(venv_python, PATH_MAX, "%s/.venv/bin/python", launcher_dir);
    if (access(venv_python, F_OK) == 0) {
        return venv_python;
    }
    return "python";
}

// Ultra-fast toggle implementation
int ultra_fast_toggle(int argc, char* argv[]) {
    const char* socket_path = "/tmp/launcher.sock";
    struct sockaddr_un addr;
    int fd;

    // Try to connect to socket
    if ((fd = socket(AF_UNIX, SOCK_STREAM, 0)) == -1) {
        return 1;
    }

    memset(&addr, 0, sizeof(addr));
    addr.sun_family = AF_UNIX;
    strncpy(addr.sun_path, socket_path, sizeof(addr.sun_path) - 1);

    struct timeval timeout = {0, 50000}; // 50ms timeout
    setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));

    if (connect(fd, (struct sockaddr*)&addr, sizeof(addr)) == 0) {
        write(fd, "SHOW", 4);
        char buf[8];
        if (read(fd, buf, 8) >= 0) {
            close(fd);
            return 0; // Success, exit
        }
    }
    close(fd);

    // No instance running, start the launcher
    char* launcher_dir = get_launcher_dir();
    if (!launcher_dir) {
        return 1;
    }

    char launcher_path[PATH_MAX];
    snprintf(launcher_path, PATH_MAX, "%s/main.py", launcher_dir);

    char* python_exe = get_python_executable(launcher_dir);
    if (chdir(launcher_dir) != 0) {
        return 1;
    }

    // Prepare arguments
    char** args = malloc((2 + argc) * sizeof(char*));
    args[0] = python_exe;
    args[1] = launcher_path;
    for (int i = 1; i < argc; i++) {
        args[i + 1] = argv[i];
    }
    args[argc + 1] = NULL;

    execvp(python_exe, args);
    free(args);
    return 1; // execvp only returns on error
}

int main(int argc, char* argv[]) {
    return ultra_fast_toggle(argc, argv);
}
