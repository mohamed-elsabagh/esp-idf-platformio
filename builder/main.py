# Copyright 2014-present PlatformIO <contact@platformio.org>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import re
from os.path import join

from SCons.Script import (AlwaysBuild, Builder, Default, DefaultEnvironment)


def _get_board_f_flash(env):
    frequency = env.subst("$BOARD_F_FLASH")
    frequency = str(frequency).replace("L", "")
    return str(int(int(frequency) / 1000000)) + "m"


env = DefaultEnvironment()
platform = env.PioPlatform()

env.Replace(
    __get_board_f_flash=_get_board_f_flash,

    AR="xtensa-esp32-elf-ar",
    AS="xtensa-esp32-elf-as",
    CC="xtensa-esp32-elf-gcc",
    CXX="xtensa-esp32-elf-g++",
    GDB="xtensa-esp32-elf-gdb",
    OBJCOPY=join(
        platform.get_package_dir("tool-esptoolpy") or "", "esptool.py"),
    RANLIB="xtensa-esp32-elf-ranlib",
    SIZETOOL="xtensa-esp32-elf-size",

    ARFLAGS=["rc"],

    ASFLAGS=["-x", "assembler-with-cpp"],

    CFLAGS=["-std=gnu99"],

    CCFLAGS=[
        "%s" % "-Os" if env.subst("$PIOFRAMEWORK") == "arduino" else "-Og",
        "-g3",
        "-nostdlib",
        "-Wpointer-arith",
        "-Wno-error=unused-but-set-variable",
        "-Wno-error=unused-variable",
        "-mlongcalls",
        "-ffunction-sections",
        "-fdata-sections",
        "-fstrict-volatile-bitfields"
    ],

    CXXFLAGS=[
        "-fno-rtti",
        "-fno-exceptions",
        "-std=gnu++11"
    ],

    CPPDEFINES=[
        "ESP32",
        "ESP_PLATFORM",
        ("F_CPU", "$BOARD_F_CPU"),
        "HAVE_CONFIG_H",
        ("MBEDTLS_CONFIG_FILE", '\\"mbedtls/esp_config.h\\"')
    ],

    LINKFLAGS=[
        "-nostdlib",
        "-Wl,-static",
        "-u", "call_user_start_cpu0",
        "-Wl,--undefined=uxTopUsedPriority",
        "-Wl,--gc-sections"
    ],

    #
    # Upload
    #

    UPLOADER=join(
        platform.get_package_dir("tool-esptoolpy") or "", "esptool.py"),
    UPLOADEROTA=join(platform.get_package_dir("tool-espotapy") or "",
                     "espota.py"),

    UPLOADERFLAGS=[
        "--chip", "esp32",
        "--port", '"$UPLOAD_PORT"',
        "--before", "default_reset",
        "--after", "hard_reset",
        "--baud", "$UPLOAD_SPEED",
        "write_flash", "-z",
        "--flash_mode", "$BOARD_FLASH_MODE",
        "--flash_freq", "${__get_board_f_flash(__env__)}",
        "--flash_size", "detect"
    ],
    UPLOADEROTAFLAGS=[
        "--debug",
        "--progress",
        "-i", "$UPLOAD_PORT",
        "-p", "3232",
        "$UPLOAD_FLAGS"
    ],

    UPLOADCMD='"$PYTHONEXE" "$UPLOADER" $UPLOADERFLAGS $SOURCE',
    UPLOADOTACMD='"$PYTHONEXE" "$UPLOADEROTA" $UPLOADEROTAFLAGS -f $SOURCE',

    SIZEPRINTCMD='$SIZETOOL -B -d $SOURCES',

    PROGNAME="firmware",
    PROGSUFFIX=".elf"
)


# Clone actual CCFLAGS to ASFLAGS
env.Append(
    ASFLAGS=env.get("CCFLAGS", [])[:]
)

#
# Framework and SDK specific configuration
#

env.Append(
    BUILDERS=dict(
        ElfToBin=Builder(
            action=env.VerboseAction(" ".join([
                '"$PYTHONEXE" "$OBJCOPY"',
                "--chip", "esp32",
                "elf2image",
                "--flash_mode", "$BOARD_FLASH_MODE",
                "--flash_freq", "${__get_board_f_flash(__env__)}",
                "--flash_size",
                env.BoardConfig().get("upload.flash_size", "4MB"),
                "-o", "$TARGET", "$SOURCES"
            ]), "Building $TARGET"),
            suffix=".bin"
        )
    )
)

if env.subst("$PIOFRAMEWORK") == "arduino":
    # Handle uploading via OTA
    ota_port = None
    if env.get("UPLOAD_PORT"):
        ota_port = re.match(
            r"\"?((([0-9]{1,3}\.){3}[0-9]{1,3})|.+\.local)\"?$",
            env.get("UPLOAD_PORT"))
    if ota_port:
        env.Replace(UPLOADCMD="$UPLOADOTACMD")

#
# Target: Build executable and linkable firmware or SPIFFS image
#

target_elf = env.BuildProgram()
if "PIOFRAMEWORK" in env:
    target_firm = env.ElfToBin(join("$BUILD_DIR", "firmware"), target_elf)

target_buildprog = env.Alias("buildprog", target_firm, target_firm)


#
# Target: Print binary size
#

target_size = env.Alias(
    "size", target_elf,
    env.VerboseAction("$SIZEPRINTCMD", "Calculating size $SOURCE"))
AlwaysBuild(target_size)

#
# Target: Upload firmware or SPIFFS image
#

target_upload = env.Alias(
    "upload", target_firm,
    [env.VerboseAction(env.AutodetectUploadPort, "Looking for upload port..."),
     env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE")])
env.AlwaysBuild(target_upload)

#
# Default targets
#

Default([target_buildprog, target_size])
