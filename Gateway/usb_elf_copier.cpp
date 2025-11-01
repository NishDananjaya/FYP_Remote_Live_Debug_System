#include <iostream>
#include <filesystem>
#include <string>
#include <sys/stat.h>
#include <unistd.h>
#include <limits.h>
#include <cstdio>

int main() {
    const char* symlink = "/dev/elf_usb";
    char buf[PATH_MAX];
    ssize_t len = readlink(symlink, buf, sizeof(buf) - 1);
    if (len < 0) {
        perror("readlink failed");
        return 1;
    }
    buf[len] = '\0';

    std::string real_dev = "/dev/" + std::string(buf);
    std::string partition = real_dev + "1";

    if (access(partition.c_str(), F_OK) != 0) {
        partition = real_dev;
    }

    std::string mount_point = "/mnt/elf_usb";
    if (mkdir(mount_point.c_str(), 0777) < 0 && errno != EEXIST) {
        perror("mkdir failed");
        return 1;
    }

    std::string mount_cmd = "mount " + partition + " " + mount_point;
    if (system(mount_cmd.c_str()) != 0) {
        std::cerr << "Mount failed. Ensure the program is run with sudo and the device is correct." << std::endl;
        return 1;
    }

    std::filesystem::path source_dir = mount_point + "/elf/";
    std::filesystem::path target_dir = "/main_module/data/elf/";

    try {
        std::filesystem::create_directories(target_dir);
        for (const auto& entry : std::filesystem::directory_iterator(source_dir)) {
            if (entry.is_regular_file() && entry.path().extension() == ".elf") {
                std::filesystem::copy(entry.path(), target_dir / entry.path().filename(),
                                      std::filesystem::copy_options::overwrite_existing);
            }
        }
    } catch (const std::filesystem::filesystem_error& e) {
        std::cerr << "Filesystem error: " << e.what() << std::endl;
    }

    std::string umount_cmd = "umount " + mount_point;
    if (system(umount_cmd.c_str()) != 0) {
        std::cerr << "Unmount failed." << std::endl;
        return 1;
    }

    std::cout << "Files copied successfully." << std::endl;
    return 0;
}
