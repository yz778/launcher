#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <errno.h>
#include <limits.h>
#include <sys/types.h>

#ifdef __linux__
#include <linux/limits.h>
#endif

// Ensure PATH_MAX is defined
#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

// Function to get the socket path (thread-safe, reentrant)
// Returns 0 on success, -1 on truncation error
static int get_socket_path(char* buffer, size_t buffer_size) {
    const char* app_name = "launcher";
    const char* runtime_dir = getenv("XDG_RUNTIME_DIR");
    uid_t uid = getuid();
    int ret;

    if (runtime_dir && strlen(runtime_dir) > 0) {
        ret = snprintf(buffer, buffer_size, "%s/%s-%u.sock", runtime_dir, app_name, uid);
    } else {
        // Fallback to /tmp if XDG_RUNTIME_DIR is not set
        ret = snprintf(buffer, buffer_size, "/tmp/%s-%u.sock", app_name, uid);
    }

    if (ret < 0 || (size_t)ret >= buffer_size) {
        return -1; // Error or truncation
    }

    return 0;
}

// Try to communicate with existing instance via Unix socket
static int try_socket_communication(void) {
    int fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (fd == -1) {
        return -1;
    }

    char socket_path[256];
    if (get_socket_path(socket_path, sizeof(socket_path)) != 0) {
        close(fd);
        return -1;
    }

    struct sockaddr_un addr = {0};
    addr.sun_family = AF_UNIX;

    // Use strncpy with proper bounds checking
    size_t path_len = strlen(socket_path);
    if (path_len >= sizeof(addr.sun_path)) {
        close(fd);
        return -1;
    }
    strncpy(addr.sun_path, socket_path, sizeof(addr.sun_path) - 1);
    addr.sun_path[sizeof(addr.sun_path) - 1] = '\0';

    // Set socket timeout
    struct timeval timeout = {.tv_sec = 0, .tv_usec = 50000}; // 50ms
    if (setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout)) == -1 ||
        setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout)) == -1) {
        close(fd);
        return -1;
    }

    if (connect(fd, (struct sockaddr*)&addr, sizeof(addr)) == 0) {
        if (write(fd, "SHOW", 4) == 4) {
            char response;
            if (read(fd, &response, 1) > 0) {
                close(fd);
                return 0; // Success
            }
        }
    }

    close(fd);
    return -1;
}

// Get the directory containing the current executable
static int get_executable_dir(char* buffer, size_t buffer_size) {
    ssize_t len = readlink("/proc/self/exe", buffer, buffer_size - 1);
    if (len == -1) {
        return -1;
    }

    buffer[len] = '\0';

    char *last_slash = strrchr(buffer, '/');
    if (!last_slash) {
        return -1;
    }

    *last_slash = '\0';
    return 0;
}

int main(int argc, char *argv[]) {
    // Try socket connection first
    if (try_socket_communication() == 0) {
        return 0; // Successfully communicated with existing instance
    }

    // Get executable directory
    char exe_dir[PATH_MAX];
    if (get_executable_dir(exe_dir, sizeof(exe_dir)) != 0) {
        fprintf(stderr, "Error: Cannot determine executable directory\n");
        return 1;
    }

    // Change to executable directory
    if (chdir(exe_dir) != 0) {
        fprintf(stderr, "Error: Cannot change to directory %s: %s\n",
                exe_dir, strerror(errno));
        return 1;
    }

    // Build path to venv python
    char venv_python[PATH_MAX];
    int ret = snprintf(venv_python, sizeof(venv_python),
                      "%s/../.venv/bin/python", exe_dir);
    if (ret < 0 || (size_t)ret >= sizeof(venv_python)) {
        fprintf(stderr, "Error: Python path too long\n");
        return 1;
    }

    // Build argument array for execvp
    // We need: python_path, "-m", "launcher.launcher", argv[1]...argv[argc-1], NULL
    size_t total_args = 3 + argc; // 3 fixed args + original args + NULL terminator
    char **args = malloc(total_args * sizeof(char*));
    if (!args) {
        fprintf(stderr, "Error: Memory allocation failed\n");
        return 1;
    }

    args[0] = venv_python;
    args[1] = "-m";
    args[2] = "launcher.launcher";

    // Copy original arguments (skip argv[0] which is the program name)
    for (int i = 1; i < argc; i++) {
        args[2 + i] = argv[i];
    }
    args[total_args - 1] = NULL;

    // Try venv python first
    execvp(venv_python, args);

    // If venv python fails, try system python
    args[0] = "python3";
    execvp("python3", args);

    // Final fallback to python
    args[0] = "python";
    execvp("python", args);

    // If we reach here, all exec attempts failed
    fprintf(stderr, "Error: Failed to execute Python interpreter\n");
    free(args);
    return 1;
}