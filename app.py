"""Watch Wise build-and-run helper (Wear OS watch face picker app).

Menu:
  1. Build the app and run it on a Wear OS emulator (watch AVD).
  2. Build the app and run it on a connected watch (adb: USB or Wi-Fi).
  3. Pair / connect a real watch over Wi-Fi (wireless debugging).
  4. Set up a Wear OS emulator (downloads the SDK tools and a Wear OS image, creates a watch AVD).
  5. Build the debug APK only.
  6. Install a watch face directly over adb (for Wear OS 4/5, where the app can't push faces).
  7. Regenerate the watch face sources (tools/gen_watchfaces.py).
  8. Show connected devices.
  9. Uninstall the app and its watch faces from a watch.
  0. Exit.
"""

import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
PACKAGE = "com.nightwise.watchwise"
LAUNCH_COMPONENT = f"{PACKAGE}/{PACKAGE}.MainActivity"
IS_WINDOWS = os.name == "nt"
GRADLEW = os.path.join(PROJECT_DIR, "gradlew.bat" if IS_WINDOWS else "gradlew")
DEBUG_APK = os.path.join(PROJECT_DIR, "app", "build", "outputs", "apk", "debug", "app-debug.apk")
EMULATOR_BOOT_TIMEOUT = 420  # seconds; a first cold boot of a new AVD is slow

SDK_REPO_URL = "https://dl.google.com/android/repository/"
SDK_REPO_XML = SDK_REPO_URL + "repository2-3.xml"
WEAR_AVD_NAME = "Wear_OS_Large_Round"
WEAR_DEVICE_PROFILE = "wearos_large_round"

# Watch Face Format faces (watchfaces/<face>), one APK per accent flavour.
FACE_PREFIX = PACKAGE + ".watchfacepush."
WATCH_FACES = {
    "monostack": ("Mono Stack", ["red", "orange", "cyan", "white"]),
    "dotmatrix": ("Dot Matrix", ["lime", "white", "cyan", "orange"]),
    "emberforest": ("Ember Forest", ["orange", "cyan", "violet", "green"]),
}


# ---------------------------------------------------------------- SDK helpers

def sdk_dir():
    """Return the Android SDK root from the environment or local.properties."""
    for var in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        value = os.environ.get(var)
        if value and os.path.isdir(value):
            return value
    props = os.path.join(PROJECT_DIR, "local.properties")
    if os.path.isfile(props):
        with open(props, encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("sdk.dir"):
                    value = line.split("=", 1)[1].strip().replace("\\:", ":").replace("\\\\", "\\")
                    if os.path.isdir(value):
                        return value
    return None


def require_sdk():
    root = sdk_dir()
    if not root:
        sys.exit("ERROR: Android SDK not found. Set ANDROID_HOME or install Android Studio.")
    return root


def tool(name):
    """Find an SDK tool (adb, emulator) or fall back to PATH."""
    root = sdk_dir()
    exe = name + (".exe" if IS_WINDOWS else "")
    if root:
        sub = "emulator" if name == "emulator" else "platform-tools"
        candidate = os.path.join(root, sub, exe)
        if os.path.isfile(candidate):
            return candidate
    found = shutil.which(name)
    if found:
        return found
    sys.exit(f"ERROR: '{name}' not found. Set ANDROID_HOME or install the Android SDK.")


def cmdline_tool(name):
    """Path to sdkmanager / avdmanager in cmdline-tools/latest, or None."""
    script = name + (".bat" if IS_WINDOWS else "")
    path = os.path.join(require_sdk(), "cmdline-tools", "latest", "bin", script)
    return path if os.path.isfile(path) else None


def tool_cmd(path, *args):
    """Command for an SDK script.

    On Windows .bat files run through cmd, which splits unquoted arguments on
    ';' ',' '=' and spaces (e.g. "system-images;android-37.0;..."), so every
    argument is quoted and the whole line is handed to `cmd /s /c "..."`.
    """
    if IS_WINDOWS and path.lower().endswith(".bat"):
        inner = " ".join(f'"{a}"' for a in (path, *args))
        return f'cmd /s /c "{inner}"'
    return [path, *args]


def run(cmd, check=True, capture=False, timeout=None, input_text=None):
    """Run a command with an argument list (no shell)."""
    return subprocess.run(
        cmd,
        cwd=PROJECT_DIR,
        check=check,
        capture_output=capture,
        text=True,
        timeout=timeout,
        input=input_text,
    )


def ask_choice(items, label):
    """Let the user pick one item from a list. Returns the item or None."""
    if len(items) == 1:
        return items[0]
    print(f"\nChoose a {label}:")
    for i, item in enumerate(items, 1):
        print(f"  {i}. {item}")
    choice = input(f"{label.capitalize()} number: ").strip()
    if not choice.isdigit() or not 1 <= int(choice) <= len(items):
        print("Invalid choice.")
        return None
    return items[int(choice) - 1]


def yes(prompt):
    return input(f"{prompt} [y/N]: ").strip().lower() in ("y", "yes")


# ---------------------------------------------------------------- build / install

def build_debug_apk():
    print("\n[build] Running assembleDebug ...")
    try:
        run(tool_cmd(GRADLEW, "assembleDebug"))
    except subprocess.CalledProcessError:
        print("[build] FAILED. Fix the errors above and try again.")
        return False
    if not os.path.isfile(DEBUG_APK):
        print(f"[build] APK not found at {DEBUG_APK}")
        return False
    print(f"[build] OK: {DEBUG_APK}")
    return True


def install_and_launch(serial):
    base = [tool("adb"), "-s", serial]
    print(f"[install] Installing APK on {serial} ...")
    run(base + ["install", "-r", DEBUG_APK])
    print("[launch] Starting Watch Wise ...")
    # Right after a (first) boot, Wear OS system UI can grab the screen just after
    # our activity starts, so check the app is really in front and retry if not.
    for _ in range(6):
        run(base + ["shell", "am", "start", "-n", LAUNCH_COMPONENT], capture=True)
        time.sleep(3)
        if app_in_front(serial):
            print("[done] Watch Wise is open on the watch - pick a face and tap 'Set face'.")
            return
        print("[launch] Watch system UI is in front, launching again ...")
    print("[launch] App installed, but could not bring it to the front. Open 'Watch Wise' from the watch's app list.")


def app_in_front(serial):
    res = run([tool("adb"), "-s", serial, "shell", "dumpsys", "activity", "activities"],
              check=False, capture=True, timeout=30)
    for line in res.stdout.splitlines():
        if "topResumedActivity" in line or "mResumedActivity" in line:
            return PACKAGE in line
    return False


# ---------------------------------------------------------------- devices

def connected_devices():
    """Return serials of devices in the 'device' state (authorized, online)."""
    out = run([tool("adb"), "devices"], capture=True).stdout
    serials = []
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) == 2 and parts[1] == "device":
            serials.append(parts[0])
    return serials


def is_watch(serial):
    """True if the device reports itself as a watch (Wear OS)."""
    res = run([tool("adb"), "-s", serial, "shell", "getprop", "ro.build.characteristics"],
              check=False, capture=True, timeout=20)
    return "watch" in res.stdout


def device_model(serial):
    res = run([tool("adb"), "-s", serial, "shell", "getprop", "ro.product.model"],
              check=False, capture=True, timeout=20)
    return res.stdout.strip() or "unknown"


def wait_for_boot(serial):
    deadline = time.time() + EMULATOR_BOOT_TIMEOUT
    while time.time() < deadline:
        res = run([tool("adb"), "-s", serial, "shell", "getprop", "sys.boot_completed"],
                  check=False, capture=True)
        if res.stdout.strip() == "1":
            return True
        time.sleep(3)
    return False


def show_devices():
    devices = connected_devices()
    if not devices:
        print("\nNo devices connected.")
        return
    print("\nConnected devices:")
    for serial in devices:
        kind = "watch" if is_watch(serial) else "phone/other"
        where = "emulator" if serial.startswith("emulator-") else "real device"
        print(f"  {serial:<40} {device_model(serial):<24} {kind}, {where}")


# ---------------------------------------------------------------- emulator (AVD)

def avd_home():
    return os.environ.get("ANDROID_AVD_HOME") or os.path.join(os.path.expanduser("~"), ".android", "avd")


def list_avds():
    out = run([tool("emulator"), "-list-avds"], capture=True).stdout
    return [line.strip() for line in out.splitlines()
            if line.strip() and not line.startswith("INFO")]


def is_wear_avd(name):
    """Read the AVD's config.ini and check that its system image is Wear OS."""
    home = avd_home()
    avd_path = os.path.join(home, name + ".avd")
    ini = os.path.join(home, name + ".ini")
    if os.path.isfile(ini):
        with open(ini, encoding="utf-8", errors="ignore") as f:
            for line in f:
                if line.startswith("path="):
                    avd_path = line.split("=", 1)[1].strip()
    config = os.path.join(avd_path, "config.ini")
    if not os.path.isfile(config):
        return False
    with open(config, encoding="utf-8", errors="ignore") as f:
        return "android-wear" in f.read()


def running_watch_emulators():
    return [d for d in connected_devices() if d.startswith("emulator-") and is_watch(d)]


def start_emulator(avd):
    """Start an AVD detached and return its adb serial once it has booted."""
    before = {d for d in connected_devices() if d.startswith("emulator-")}
    print(f"[emulator] Starting {avd} (first boot can take a few minutes) ...")
    # Detached so the emulator keeps running after this script exits.
    flags = {"creationflags": subprocess.DETACHED_PROCESS} if IS_WINDOWS else {"start_new_session": True}
    subprocess.Popen([tool("emulator"), "-avd", avd], cwd=PROJECT_DIR,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **flags)
    print("[emulator] Waiting for the watch to appear ...")
    deadline = time.time() + EMULATOR_BOOT_TIMEOUT
    serial = None
    while time.time() < deadline and not serial:
        new = [d for d in connected_devices() if d.startswith("emulator-") and d not in before]
        serial = new[0] if new else None
        if not serial:
            time.sleep(3)
    if not serial:
        print("Emulator did not appear. Open it from Android Studio > Device Manager to see why.")
        return None
    print(f"[emulator] {serial} is up, waiting for boot to finish ...")
    if not wait_for_boot(serial):
        print("Emulator did not finish booting in time. Try option 1 again once it is on the watch face.")
        return None
    return serial


def run_on_emulator():
    running = running_watch_emulators()
    if running:
        serial = ask_choice(running, "running watch emulator")
        if not serial:
            return
        print(f"\nWatch emulator already running: {serial}")
    else:
        wear_avds = [a for a in list_avds() if is_wear_avd(a)]
        if not wear_avds:
            print("\nNo Wear OS emulator found.")
            if yes("Set one up now (downloads ~1-2 GB)?"):
                if not setup_wear_emulator():
                    return
                wear_avds = [a for a in list_avds() if is_wear_avd(a)]
            if not wear_avds:
                return
        avd = ask_choice(wear_avds, "watch emulator")
        if not avd:
            return
        if not build_debug_apk():
            return
        serial = start_emulator(avd)
        if not serial:
            return
        install_and_launch(serial)
        return
    if build_debug_apk():
        install_and_launch(serial)


# ---------------------------------------------------------------- real watch

def run_on_watch():
    real = [d for d in connected_devices() if not d.startswith("emulator-")]
    watches = [d for d in real if is_watch(d)]
    if not watches:
        print("\nNo real watch found over adb.")
        if real:
            print("(Other devices are connected, but none report as a Wear OS watch.)")
        print("Connect the watch with option 3 (Wi-Fi), or by USB if it has a cable/dock,")
        print("with Developer options > ADB debugging turned on.")
        return
    serial = ask_choice(watches, "watch")
    if not serial:
        return
    print(f"\nWatch: {serial} ({device_model(serial)})")
    if build_debug_apk():
        install_and_launch(serial)


def connect_watch_wifi():
    adb = tool("adb")
    print("""
On the watch:
  1. Settings > System > About > tap 'Build number' 7 times (enables Developer options).
  2. Settings > Developer options > turn on 'ADB debugging' and 'Wireless debugging'.
  3. Keep the watch and this PC on the same Wi-Fi network.
""")
    print("Step A - Pair (only needed the first time).")
    print("  On the watch: Wireless debugging > 'Pair new device'. It shows an IP:port and a code.")
    pair_addr = input("  Pairing IP:port (press Enter to skip if already paired): ").strip()
    if pair_addr:
        if ":" not in pair_addr:
            print("  That has no port. Enter it exactly as the pairing screen shows it, e.g. 192.168.0.102:41235")
            return
        code = input("  Pairing code (6 digits): ").strip().replace(" ", "")
        if not (code.isdigit() and len(code) == 6):
            print("  The pairing code is 6 digits. Check the watch screen and try again.")
            return
        res = run([adb, "pair", pair_addr, code], check=False, capture=True, timeout=60)
        print("  " + (res.stdout + res.stderr).strip())
        if "Successfully paired" not in res.stdout:
            print("  Pairing failed. Check the IP:port and code (the code expires quickly).")
            return
    print("\nStep B - Connect.")
    print("  On the watch: the main 'Wireless debugging' screen shows 'IP address & port'.")
    conn_addr = input("  Connect IP:port: ").strip()
    if not conn_addr:
        print("  Skipped.")
        return
    if ":" not in conn_addr:
        print("  That has no port. Use the 'IP address & port' from the main Wireless debugging screen.")
        return
    res = run([adb, "connect", conn_addr], check=False, capture=True, timeout=60)
    print("  " + (res.stdout + res.stderr).strip())
    if "connected to" in res.stdout:
        print("\nWatch connected. Use option 2 to run the app on it.")


# ---------------------------------------------------------------- uninstall

def face_packages():
    return [f"{FACE_PREFIX}{face}_{accent}" for face, (_, accents) in WATCH_FACES.items() for accent in accents]


def uninstall_app():
    watches = [d for d in connected_devices() if is_watch(d)]
    if not watches:
        print("\nNo watch (real or emulator) connected.")
        return
    serial = ask_choice(watches, "watch")
    if not serial:
        return
    adb = [tool("adb"), "-s", serial]
    res = run(adb + ["uninstall", PACKAGE], check=False, capture=True)
    print(f"{PACKAGE}: " + ((res.stdout + res.stderr).strip() or "done"))
    installed = run(adb + ["shell", "pm", "list", "packages", FACE_PREFIX], check=False, capture=True).stdout
    for pkg in face_packages():
        if f"package:{pkg}" in installed:
            res = run(adb + ["uninstall", pkg], check=False, capture=True)
            print(f"{pkg}: " + ((res.stdout + res.stderr).strip() or "done"))


# ---------------------------------------------------------------- watch faces (direct install)

def install_face_direct():
    """Build one WFF face APK and adb-install it (no Watch Face Push needed)."""
    watches = [d for d in connected_devices() if is_watch(d)]
    if not watches:
        print("\nNo watch (real or emulator) connected.")
        return
    serial = ask_choice(watches, "watch")
    if not serial:
        return
    faces = list(WATCH_FACES)
    face = ask_choice([f"{f} ({WATCH_FACES[f][0]})" for f in faces], "watch face")
    if not face:
        return
    face = face.split(" ")[0]
    accent = ask_choice(WATCH_FACES[face][1], "accent")
    if not accent:
        return
    task = f":watchfaces:{face}:assemble{accent.capitalize()}Release"
    print(f"\n[build] {task} ...")
    try:
        run(tool_cmd(GRADLEW, task))
    except subprocess.CalledProcessError:
        print("[build] FAILED.")
        return
    apk = os.path.join(PROJECT_DIR, "watchfaces", face, "build", "outputs", "apk", accent, "release",
                       f"{face}-{accent}-release.apk")
    adb = [tool("adb"), "-s", serial]
    print(f"[install] {os.path.basename(apk)} ...")
    run(adb + ["install", "-r", apk])
    pkg = f"{FACE_PREFIX}{face}_{accent}"
    # Developer shortcut to switch the watch face (works on emulators / debuggable builds).
    run(adb + ["shell", "am", "broadcast", "-a", "com.google.android.wearable.app.DEBUG_SURFACE",
               "--es", "operation", "set-watchface", "--es", "watchFaceId", pkg], check=False, capture=True)
    print(f"[done] Installed {WATCH_FACES[face][0]} ({accent}). If it isn't showing, long-press the")
    print("       watch face and pick it from the list.")


def regenerate_faces():
    """Run tools/gen_watchfaces.py (needs fonttools + pillow)."""
    script = os.path.join(PROJECT_DIR, "tools", "gen_watchfaces.py")
    check = run([sys.executable, "-c", "import fontTools, PIL"], check=False, capture=True)
    if check.returncode != 0:
        print("\nThe generator needs fonttools and pillow:")
        print(f"  {sys.executable} -m pip install fonttools pillow")
        return
    run([sys.executable, script])
    print("[done] Rebuild the app (option 1/2/5) to bundle the updated faces.")


# ---------------------------------------------------------------- Wear emulator setup

def download(url, dest):
    print(f"[download] {url}")
    with urllib.request.urlopen(url, timeout=60) as resp, open(dest, "wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if total:
                print(f"\r[download] {done * 100 // total:3d}%  ({done >> 20} / {total >> 20} MB)",
                      end="", flush=True)
    print()


def latest_cmdline_tools_archive():
    """Return (url, sha1) of the cmdline-tools;latest zip for this OS from Google's SDK repo."""
    host = {"nt": "windows", "posix": "macosx" if sys.platform == "darwin" else "linux"}[os.name]
    with urllib.request.urlopen(SDK_REPO_XML, timeout=60) as resp:
        root = ET.fromstring(resp.read())
    for pkg in root.iter():
        if pkg.tag.split("}")[-1] != "remotePackage" or pkg.get("path") != "cmdline-tools;latest":
            continue
        for archive in pkg.iter():
            if archive.tag.split("}")[-1] != "archive":
                continue
            fields = {el.tag.split("}")[-1]: (el.text or "").strip() for el in archive.iter()}
            if fields.get("host-os") == host and fields.get("url"):
                return SDK_REPO_URL + fields["url"], fields.get("checksum")
    return None, None


def install_cmdline_tools():
    """Download the Android SDK command-line tools into <sdk>/cmdline-tools/latest."""
    print("\n[setup] Android SDK command-line tools (sdkmanager, avdmanager) are missing.")
    url, sha1 = latest_cmdline_tools_archive()
    if not url:
        print("[setup] Could not find the download in Google's SDK repository.")
        print("        Install them from Android Studio: SDK Manager > SDK Tools > 'Android SDK Command-line Tools'.")
        return False
    target = os.path.join(require_sdk(), "cmdline-tools", "latest")
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = os.path.join(tmp, "cmdline-tools.zip")
        download(url, zip_path)
        if sha1:
            h = hashlib.sha1()
            with open(zip_path, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
            if h.hexdigest().lower() != sha1.lower():
                print("[setup] Checksum mismatch, download is corrupt. Try again.")
                return False
        extract_dir = os.path.join(tmp, "extract")
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_dir)
        src = os.path.join(extract_dir, "cmdline-tools")
        if not os.path.isdir(src):
            print("[setup] Unexpected archive layout.")
            return False
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.move(src, target)
    if not IS_WINDOWS:
        for name in ("sdkmanager", "avdmanager"):
            os.chmod(os.path.join(target, "bin", name), 0o755)
    print(f"[setup] Installed command-line tools to {target}")
    return True


def installed_wear_images():
    """Installed Wear OS x86_64 system image package ids, newest first."""
    base = os.path.join(require_sdk(), "system-images")
    found = []
    if os.path.isdir(base):
        for api in os.listdir(base):
            for tag in ("android-wear-signed", "android-wear"):
                if os.path.isdir(os.path.join(base, api, tag, "x86_64")):
                    found.append(f"system-images;{api};{tag};x86_64")
    return sorted(found, key=api_level, reverse=True)


def api_level(package):
    m = re.search(r"android-(\d+(?:\.\d+)?)", package)
    return float(m.group(1)) if m else 0.0


def available_wear_images(sdkmanager):
    """Wear OS x86_64 system images in the SDK repository, newest first."""
    print("[setup] Asking sdkmanager for available Wear OS images ...")
    out = run(tool_cmd(sdkmanager, "--list"), capture=True, check=False).stdout
    # sdkmanager prints ids with ';' or '/' separators, e.g.
    # system-images/android-37.0/android-wear-signed/x86_64 (newer images are "-signed").
    found = re.findall(r"system-images[;/](android-[\w.-]+)[;/](android-wear(?:-signed)?)[;/]x86_64", out)
    images = {f"system-images;{api};{tag};x86_64" for api, tag in found}
    return sorted(images, key=api_level, reverse=True)


def setup_wear_emulator():
    """Make sure a Wear OS system image and a watch AVD exist. Returns True on success."""
    sdkmanager = cmdline_tool("sdkmanager")
    if not sdkmanager:
        if not install_cmdline_tools():
            return False
        sdkmanager = cmdline_tool("sdkmanager")
    avdmanager = cmdline_tool("avdmanager")

    image = (installed_wear_images() or [None])[0]
    if image:
        print(f"[setup] Wear OS image already installed: {image}")
    else:
        images = available_wear_images(sdkmanager)
        if not images:
            print("[setup] No Wear OS x86_64 image found. Use Android Studio > Device Manager instead.")
            return False
        image = images[0]
        print(f"[setup] Installing {image} (large download; accept the license if asked) ...")
        try:
            # stdin is inherited so you can answer the license prompt.
            run(tool_cmd(sdkmanager, "--install", image, "emulator", "platform-tools"))
        except subprocess.CalledProcessError:
            print("[setup] sdkmanager failed. See the output above.")
            return False

    existing = [a for a in list_avds() if is_wear_avd(a)]
    if WEAR_AVD_NAME in list_avds():
        print(f"[setup] Watch emulator '{WEAR_AVD_NAME}' already exists.")
        return True
    print(f"[setup] Creating watch emulator '{WEAR_AVD_NAME}' ({WEAR_DEVICE_PROFILE}) ...")
    res = run(tool_cmd(avdmanager, "create", "avd", "-n", WEAR_AVD_NAME, "-k", image,
                       "-d", WEAR_DEVICE_PROFILE),
              check=False, capture=True, input_text="no\n")
    if res.returncode != 0:
        print((res.stdout + res.stderr).strip())
        print("[setup] Could not create the AVD.")
        return bool(existing)
    print(f"[setup] Done. '{WEAR_AVD_NAME}' is ready - use option 1 to run the app on it.")
    return True


# ---------------------------------------------------------------- menu

def menu():
    print("\n==============================")
    print(" Watch Wise - Wear OS runner")
    print("==============================")
    print(" 1. Run app in Emulator watch")
    print(" 2. Run app in Connected watch (adb)")
    print(" 3. Connect a watch over Wi-Fi (pair + connect)")
    print(" 4. Set up Wear OS emulator")
    print(" 5. Build debug APK only")
    print(" 6. Install a watch face directly (adb, Wear OS 4/5)")
    print(" 7. Regenerate watch face sources")
    print(" 8. Show connected devices")
    print(" 9. Uninstall app + watch faces from a watch")
    print(" 0. Exit")
    return input("Select an option: ").strip()


ACTIONS = {
    "1": run_on_emulator,
    "2": run_on_watch,
    "3": connect_watch_wifi,
    "4": setup_wear_emulator,
    "5": build_debug_apk,
    "6": install_face_direct,
    "7": regenerate_faces,
    "8": show_devices,
    "9": uninstall_app,
}


def main():
    while True:
        try:
            choice = menu()
            if choice == "0":
                print("Bye.")
                return
            action = ACTIONS.get(choice)
            if action:
                action()
            else:
                print("Please enter a number from the menu.")
        except subprocess.CalledProcessError as exc:
            print(f"\nCommand failed (exit {exc.returncode}): {' '.join(map(str, exc.cmd))}")
        except subprocess.TimeoutExpired:
            print("\nTimed out waiting for a device.")
        except OSError as exc:
            print(f"\nError: {exc}")
        except KeyboardInterrupt:
            print("\nCancelled.")
            return


if __name__ == "__main__":
    main()
