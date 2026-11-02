# First-time setup: Android, Better Hall Aircon, and token capture

For a Windows computer and an Android phone, including **Xiaomi 15T Pro, model 2506BPN68G**. The emulator procedure below successfully captured and validated a token on **3 November 2026**. Start at step 1 on a fresh setup; nothing below assumes commands from a previous chat.

For an existing setup with an expired or revoked token, use the separate [token renewal guide](/C:/Users/User/Desktop/python/personal/Better-Hall-Aircon/ANDROID_TOKEN_RENEWAL.md).

## Choose the capture route

| Route | When to use it |
| --- | --- |
| **Recommended: Windows Android emulators** | This is the method that worked with your Xiaomi account and current Hall Aircon app. Follow steps 1–11. The physical phone is used to confirm your account and room; capture happens in an emulator. |
| **Capture directly from the physical Android phone** | An optional attempt is documented in section 12. It requires the app to accept a user-installed CA. Your Xiaomi setup reached the VPN successfully but the app rejected that certificate. |

`HandshakeException` / `CERTIFICATE_VERIFY_FAILED` concerns HTTPS certificate trust. It is different from a missing WireGuard handshake. Modern Android apps do not trust user-installed CAs by default; installing one in Settings does not force every app to accept it. [Android certificate-trust documentation](https://developer.android.com/privacy-and-security/security-config)

The successful route installs the capture CA in a root-capable emulator's **system** certificate store. It does not require rooting the Xiaomi.

## 1. Confirm your account and room on the Android phone

1. Install **Hall Aircon by Daikin Singapore** from its [official Play Store listing](https://play.google.com/store/apps/details?id=sg.daikin.ntu.ntu_mobile).
2. Sign into your own account. If pairing is required, scan your own room's wall QR code.
3. Confirm that the room's status loads normally. Resolve account, pairing, balance or device-offline problems before attempting capture.
4. Keep the room QR code or its complete printed device number available for the Windows program.

A status refresh is sufficient for setup; switching the aircon on is unnecessary.

## 2. Install the Windows tools

You need internet access, permission to approve the program's Windows firewall prompt, a Google account for the emulator's Play Store, and sufficient storage for two Android system images.

### Better Hall Aircon

Download the Windows portable package from the project's [official releases](https://github.com/QR-Not-Code/Better-Hall-Aircon/releases/latest). Extract the whole archive and run `HallAirconStudio.exe` with its accompanying files intact. If you already run this project successfully, use that installation.

An already working source checkout can be used instead. The portable Windows route above needs no separate Python installation.

### Android Studio and SDK

Install [Android Studio for Windows](https://developer.android.com/studio). Complete its first-run setup and SDK licence prompts. In **SDK Manager → SDK Tools**, ensure **Android SDK Platform-Tools** and **Android Emulator** are installed.

This guide assumes the default SDK directory `%LOCALAPPDATA%\Android\Sdk`. If you chose another location, change `$airconSdk` in the command blocks accordingly. If the emulator reports missing acceleration, follow [Google's Windows emulator acceleration instructions](https://developer.android.com/studio/run/emulator-acceleration).

### OpenSSL

Certificate naming uses OpenSSL. This computer's installation is at `C:\Program Files\Git\usr\bin\openssl.exe`. If that file is absent, install [Git for Windows](https://git-scm.com/install/windows) in its default location, or adjust `$opensslPath` to your own OpenSSL executable.

## 3. Prepare the room, computer address and capture files

In **Better Hall Aircon on Windows**:

1. Open the connection/setup page and choose **Get Token / First-time connection**, rather than the existing-token import route.
2. Paste the complete room QR contents or select a clear QR photograph. Check the detected room and click **Save device number**.
3. Stop any existing capture. Refresh the computer address list and select the current **physical Wi-Fi or Ethernet IPv4 address**. Use `ipconfig` if needed to identify the active adapter.
4. Click **① Prepare connection QR code**. This generates the program's CA certificate and a WireGuard configuration file.
5. Click **② Configure firewall**, approve the Windows administrator prompt, and check the result.
6. Keep the capture purpose on **Get authorization / stop automatically**. Leave the engine stopped until step 10.

The address `192.168.0.100` worked in the verified session; it is an example, not a permanent setting. Select an address currently assigned to this PC. Avoid an unrelated ZeroTier/VPN adapter, an inactive adapter, the phone's address, or assuming the hotspot example `192.168.137.1` applies.

This emulator route uses the PC's existing network connection. A Windows mobile hotspot is unnecessary. The program opens **UDP 51820** for the selected address; it is not an HTTP proxy on TCP 8080. Preparing a new address does not itself refresh an old firewall rule, so rerun button ② after address changes.

Generated files are under `%LOCALAPPDATA%\HallAirconStudio\capture`. The certificate needed below is **`mitmproxy-ca-cert.cer`**. Preserve this directory because it also contains the capture CA and tunnel keys.

## 4. Create two separate virtual devices

Open **Android Studio → More Actions → Virtual Device Manager**, or **Tools → Device Manager**. Create both of these devices:

| Name to enter exactly | Phone profile | Android / API | Services / image | Job |
| --- | --- | --- | --- | --- |
| **HallAircon_Play_API33** | Pixel 4, with Play Store support | Android 13 / Tiramisu / **33** | **Google Play**, **x86_64** | Download the compatible official app |
| **HallAircon_API33** | Pixel 4a | Android 13 / Tiramisu / **33** | **Google APIs**, **x86_64** | Capture traffic with a system-trusted CA |

Use other image lists/filters or SDK Manager if API 33 is not immediately shown. Keep **both devices configured**, but run **only one at a time** throughout the transfer procedure.

The names identify the devices; the selected **system image** determines their capabilities. Renaming a Google Play device does not turn it into a root-capable Google APIs device. Google Play images block ordinary `adb root`. [Virtual-device documentation](https://developer.android.com/studio/run/managing-avds)

The app examined in the verified setup was version 1.0.15 with **minimum API 32**. Android 11 / API 30 and ordinary Android 12 / API 31 were too old. API 33 worked. Future app versions may have different requirements. Android 14+ also changes certificate-store handling, so selecting a newer image is not automatically a substitute for this tested procedure.

The API 33 capture image was **x86_64 only** without ARM translation. Copying the app from the ARM64 Xiaomi failed. Obtain the package set from the Play emulator instead, as follows.

## 5. Initialize the PowerShell working window

Use two PowerShell windows:

- **Window A:** later launches the capture emulator and stays open while it runs.
- **Window B:** runs all other command blocks in this guide.

Open **Window B** and paste this entire initialization block. If you close that window, open another and rerun this block before continuing. The app package folder is recorded on disk for reuse.

```powershell
$airconSdk = Join-Path $env:LOCALAPPDATA 'Android\Sdk'
$adbPath = Join-Path $airconSdk 'platform-tools\adb.exe'
$workDir = Join-Path $env:LOCALAPPDATA 'HallAirconStudio\emulator-setup'
$captureDir = Join-Path $env:LOCALAPPDATA 'HallAirconStudio\capture'
$opensslPath = 'C:\Program Files\Git\usr\bin\openssl.exe'
foreach ($requiredFile in @($adbPath, $opensslPath)) {
    if (-not (Test-Path -LiteralPath $requiredFile)) { throw ('Required tool not found: ' + $requiredFile) }
}
New-Item -ItemType Directory -Path $workDir -Force | Out-Null
function Confirm-AirconDevice {
    param([string]$ExpectedName)
    $avdLines = @(& $adbPath -e emu avd name)
    if ($LASTEXITCODE -ne 0 -or $ExpectedName -notin @($avdLines | ForEach-Object { $_.Trim() })) {
        throw ('Run only ' + $ExpectedName + ' and wait for its home screen.')
    }
    $bootLines = @(& $adbPath -e shell getprop sys.boot_completed)
    if (($bootLines -join '').Trim() -ne '1') { throw 'Android is still booting. Wait and rerun the check.' }
}
& $adbPath devices
```

`-e` targets the single running emulator, so an attached physical phone is not selected. Stop if a command throws an error; resolve it before running dependent blocks. [ADB device selection and installation](https://developer.android.com/tools/adb)

## 6. Download and copy the matching Hall Aircon packages

1. Start **HallAircon_Play_API33** normally in Device Manager. Leave the capture device stopped.
2. Wait for Android to boot. Open its Play Store and sign into your Google account.
3. Install **Hall Aircon by Daikin Singapore**. Its package is `sg.daikin.ntu.ntu_mobile`.
4. If the store reports incompatibility, stop this route and keep the exact message. A matching build has not been established for that new setup.

Signing into Hall Aircon inside the Play emulator is unnecessary for copying its installation files. Google Play supplies packages for the receiving device configuration. [App bundle delivery](https://developer.android.com/guide/app-bundle)

In **Window B**, copy every package from this installation into a new folder:

```powershell
Confirm-AirconDevice 'HallAircon_Play_API33'
$playApkDir = Join-Path $workDir ('HallAircon-Play-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $playApkDir | Out-Null
$packagePaths = @(& $adbPath -e shell pm path sg.daikin.ntu.ntu_mobile | Where-Object { $_ -like 'package:*' })
if ($packagePaths.Count -eq 0) { throw 'Hall Aircon is not installed on the Play emulator.' }
foreach ($packagePath in $packagePaths) {
    $remoteApk = $packagePath.Trim().Substring(8)
    & $adbPath -e pull $remoteApk $playApkDir
    if ($LASTEXITCODE -ne 0) { throw 'An APK copy failed.' }
}
$playApkFiles = @(Get-ChildItem -LiteralPath $playApkDir -Filter '*.apk' | ForEach-Object { $_.FullName })
```

Verify the copied native libraries before switching devices:

```powershell
Add-Type -AssemblyName System.IO.Compression.FileSystem
$playNativeAbis = @($playApkFiles | ForEach-Object {
    $apkArchive = [System.IO.Compression.ZipFile]::OpenRead($_)
    try {
        $apkArchive.Entries | Where-Object { $_.FullName -match '^lib/[^/]+/.+\.so$' } | ForEach-Object { $_.FullName.Split('/')[1] }
    } finally {
        $apkArchive.Dispose()
    }
} | Sort-Object -Unique)
$playNativeAbis
if ('x86_64' -notin $playNativeAbis) { throw 'This package set lacks x86_64 libraries. Stop before installation.' }
Set-Content -LiteralPath (Join-Path $workDir 'play-apk-folder.txt') -Value $playApkDir -Encoding UTF8
```

**Checkpoint:** output includes `x86_64`. The successful setup had five packages, including `split_config.x86_64.apk`; other versions can have a different count. Transfer the complete set from one installation, without mixing in Xiaomi packages.

## 7. Launch the capture emulator and install the app

Close **HallAircon_Play_API33**. In **Window A**, run:

```powershell
$emulatorPath = Join-Path $env:LOCALAPPDATA 'Android\Sdk\emulator\emulator.exe'
& $emulatorPath -avd HallAircon_API33 -writable-system -no-snapshot
```

Leave Window A open and wait for Android's home screen. Use this launch command for future capture sessions too.

In **Window B**, check the device and install the saved package set:

```powershell
Confirm-AirconDevice 'HallAircon_API33'
$sdkLines = @(& $adbPath -e shell getprop ro.build.version.sdk)
$debugLines = @(& $adbPath -e shell getprop ro.debuggable)
if (($sdkLines -join '').Trim() -ne '33') { throw 'The capture image must run API 33 for this procedure.' }
if (($debugLines -join '').Trim() -ne '1') { throw 'Wrong image: create a separate Google APIs capture device.' }
$packageRecord = Join-Path $workDir 'play-apk-folder.txt'
if (-not (Test-Path -LiteralPath $packageRecord)) { throw 'Complete the Play package copy and ABI check first.' }
$playApkDir = (Get-Content -LiteralPath $packageRecord -Raw).Trim()
$playApkFiles = @(Get-ChildItem -LiteralPath $playApkDir -Filter '*.apk' | ForEach-Object { $_.FullName })
if ($playApkFiles.Count -eq 0) { throw 'The saved package folder is empty.' }
if ($playApkFiles.Count -eq 1) {
    & $adbPath -e install -r $playApkFiles[0]
} else {
    & $adbPath -e install-multiple -r @playApkFiles
}
if ($LASTEXITCODE -ne 0) { throw 'Hall Aircon installation failed. Keep the exact error.' }
& $adbPath -e root
if ($LASTEXITCODE -ne 0) { throw 'Root access failed.' }
& $adbPath -e wait-for-device
& $adbPath -e shell id
```

**Checkpoint:** installation prints `Success`; root reports that adbd restarted as root or is already root; `id` reports `uid=0(root)`.

## 8. Install and verify the system capture certificate

Perform all blocks in **Window B**. They apply to **HallAircon_API33** only. Use the CA generated in step 3; its name alone does not establish that it matches a previous installation.

Prepare the public CA with its calculated Android filename:

```powershell
Confirm-AirconDevice 'HallAircon_API33'
$caCert = Join-Path $captureDir 'mitmproxy-ca-cert.cer'
if (-not (Test-Path -LiteralPath $caCert)) { throw 'Click Prepare connection QR code in Better Hall Aircon first.' }
$hashOutput = @(& $opensslPath x509 -in $caCert -noout -subject_hash_old)
if ($LASTEXITCODE -ne 0) { throw 'OpenSSL could not read the capture CA.' }
$caHash = ($hashOutput | Select-Object -First 1).Trim()
if ($caHash -notmatch '^[0-9a-fA-F]{8}$') { throw 'Unexpected certificate hash.' }
$namedCert = Join-Path $workDir ($caHash + '.0')
Copy-Item -LiteralPath $caCert -Destination $namedCert -Force
$androidCert = '/system/etc/security/cacerts/' + $caHash + '.0'
```

OpenSSL documents the [subject-hash option](https://docs.openssl.org/3.0/man1/openssl-x509/). The certificate filename and system location follow [mitmproxy's Android CA method](https://docs.mitmproxy.org/stable/howto/install-system-trusted-ca-android/).

Prepare the system for writing:

```powershell
& $adbPath -e root
& $adbPath -e wait-for-device
& $adbPath -e disable-verity
if ($LASTEXITCODE -ne 0) { throw 'Could not disable emulator verity.' }
& $adbPath -e reboot
```

**Wait for the emulator's home screen after this reboot.** Then run:

```powershell
Confirm-AirconDevice 'HallAircon_API33'
& $adbPath -e root
& $adbPath -e wait-for-device
& $adbPath -e remount
if ($LASTEXITCODE -ne 0) { throw 'Remount failed. Resolve it before copying the CA.' }
```

If remount requests another reboot, run the following, wait for the home screen, and repeat the preceding root/remount block:

```powershell
& $adbPath -e reboot
```

Continue only after remount succeeds without a further reboot request. This follows Android's [root/remount procedure](https://android.googlesource.com/platform/system/core/+/refs/heads/main/fs_mgr/README.overlayfs.md).

```powershell
& $adbPath -e push $namedCert $androidCert
if ($LASTEXITCODE -ne 0) { throw 'Certificate copy failed.' }
& $adbPath -e shell chmod 644 $androidCert
if ($LASTEXITCODE -ne 0) { throw 'Certificate permissions failed.' }
& $adbPath -e shell chown 0:0 $androidCert
if ($LASTEXITCODE -ne 0) { throw 'Certificate ownership failed.' }
& $adbPath -e shell restorecon $androidCert
if ($LASTEXITCODE -ne 0) { throw 'Certificate file context failed.' }
& $adbPath -e reboot
```

Wait for the home screen again. Verify the installed bytes after reboot:

```powershell
Confirm-AirconDevice 'HallAircon_API33'
$verifiedCert = Join-Path $workDir 'verified-system-ca.cer'
& $adbPath -e pull $androidCert $verifiedCert
if ($LASTEXITCODE -ne 0) { throw 'The system certificate is missing after reboot.' }
if ((Get-FileHash -LiteralPath $verifiedCert -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath $caCert -Algorithm SHA256).Hash) {
    throw 'The installed system CA does not match this capture installation.'
}
'System certificate matches the current capture CA.'
```

You can also search emulator Settings for **Trusted credentials** and find `mitmproxy` under **System**. App-level HTTPS trust is checked in step 10.

The writable system is temporary. Closing the emulator can discard its system changes; use the same launch flags and check/reinstall the CA in the next session. Installed apps and their user data normally persist. [Writable-system behaviour](https://developer.android.com/studio/run/emulator-commandline)

## 9. Install WireGuard in the capture emulator

On Windows, open [WireGuard's official installation page](https://www.wireguard.com/install/). Under **Android**, follow **Download APK File**, then download the APK offered by the official download page. Save it as **`wireguard.apk`** in your Windows Downloads folder.

In **Window B**:

```powershell
Confirm-AirconDevice 'HallAircon_API33'
$wireguardApk = Join-Path $env:USERPROFILE 'Downloads\wireguard.apk'
if (-not (Test-Path -LiteralPath $wireguardApk)) { throw 'Save the official WireGuard APK in Downloads as wireguard.apk.' }
& $adbPath -e install -r $wireguardApk
if ($LASTEXITCODE -ne 0) { throw 'WireGuard installation failed.' }
```

**Checkpoint:** `Success`. WireGuard Android 1.0.20260315 worked in the verified setup; the official site may offer a newer version later.

## 10. Connect the emulator and capture the token

1. Keep the Xiaomi's WireGuard tunnel off. Only the capture emulator should use this generated tunnel during capture.
2. In Better Hall Aircon, recheck the selected PC address. If it changed since step 3, stop capture, select the new address, click **① Prepare**, and rerun **② Configure firewall**.
3. In **Window B**, display only the non-secret Endpoint and copy the current configuration:

```powershell
Confirm-AirconDevice 'HallAircon_API33'
$phoneProfile = Join-Path $captureDir 'phone.conf'
if (-not (Test-Path -LiteralPath $phoneProfile)) { throw 'Prepare the connection in Better Hall Aircon first.' }
Get-Content -LiteralPath $phoneProfile | Select-String -Pattern '^Endpoint\s*='
& $adbPath -e push $phoneProfile /sdcard/Download/hall-aircon.conf
if ($LASTEXITCODE -ne 0) { throw 'Tunnel file copy failed.' }
```

4. In the **capture emulator**, open **WireGuard → + → Import from file or archive → Downloads → hall-aircon.conf**. This replaces the need for an emulator camera/QR scan.
5. Check that Endpoint matches the PC address selected in Better Hall Aircon and port **51820**. Leave generated keys, address `10.0.0.1/32`, DNS `10.0.0.53`, Allowed IPs `0.0.0.0/0`, and keepalive unchanged.
6. On Windows, select **Get authorization / stop automatically**, then click **③ Start and wait for authorization**. Wait for **Capture engine ready**.
7. In emulator WireGuard, enable the imported tunnel and accept the Android VPN prompt. Expect a recent handshake and sent/received traffic. Windows should report a recent connection.
8. In the emulator browser, enter the full **http://mitm.it** address. Expect the mitmproxy certificate page. The system CA is already installed.
9. Open **Hall Aircon in the capture emulator**. Sign into your own account, including any normal SSO/MFA steps, and refresh your own room's status. The Play emulator's login session was not copied.
10. Wait for the Windows program to report **Token acquired / aircon connected** and show the correct room. It extracts the Bearer token, checks `/me` against the saved room, saves the token encrypted, and normally stops capture automatically.

**Success is the room-validated token result**, rather than just a green VPN switch. Avoid switching aircon power simply to generate traffic; signing in and refreshing status worked for this setup.

## 11. Finish and preserve the reusable setup

1. Once capture stops, **turn off the emulator's WireGuard tunnel** to restore normal connectivity.
2. Enter Better Hall Aircon's control panel and click **Refresh status**. Confirm a successful response for the correct room.
3. Copy the complete token from the program's result window only if you need it elsewhere. Keep tokens and tunnel configurations private.
4. You can close the emulator. Better Hall Aircon uses its saved token without the emulator or capture engine running. Local scripts still require the Windows program/computer to run.

Preserve both AVDs and `%LOCALAPPDATA%\HallAirconStudio`. That directory holds the encrypted vault, room settings, capture CA and WireGuard keys. The helper directory `emulator-setup` records the compatible Play APK folder. Routine token renewal should not require recreating devices or recopying apps.

When authorization expires or is revoked, follow [Renew an Android token](/C:/Users/User/Desktop/python/personal/Better-Hall-Aircon/ANDROID_TOKEN_RENEWAL.md).

## 12. Optional: capture directly on the physical Android phone

This is conditional and did **not** complete on the tested stock Xiaomi because of certificate trust. If you choose to try it, complete step 1, the **Better Hall Aircon** subsection of step 2, and step 3. The emulator/Git/SDK steps are unnecessary for this attempt.

1. Put the phone and PC on a mutually reachable network. The same router works if client isolation is disabled. If a Windows hotspot is unavailable, you can try connecting the PC to the Xiaomi's mobile hotspot; use the **PC's assigned address** as Endpoint and ensure mobile data provides internet.
2. Select that actual PC IPv4 address in Better Hall Aircon, then click **① Prepare**, **② Configure firewall**, and approve Windows' prompt.
3. Install the [official Android WireGuard client](https://www.wireguard.com/install/). Stop other phone VPNs, including VPN-based capture/ad-blocking apps.
4. In WireGuard, choose **+ → Scan from QR code**, scan Better Hall Aircon's connection QR, and save the tunnel. This is different from the room QR used by Hall Aircon.
5. Start Windows capture with button **③**, wait for ready, then enable the phone tunnel and grant VPN permission.
6. Check for a recent handshake and received traffic. Open **http://mitm.it** in the phone browser and download the **Android** CA from this running capture installation.
7. In Xiaomi Settings, search **Encryption & credentials** or **Install a certificate**. Choose **CA certificate**, select the downloaded CA and confirm using your screen lock. Do not choose a Wi-Fi or client identity certificate category. Menu names vary with HyperOS.
8. Force-stop and reopen Hall Aircon, sign in if needed, and refresh room status. If the Windows program captures and validates the token, follow step 11's cleanup.
9. If Hall Aircon now reports `CERTIFICATE_VERIFY_FAILED` despite the current CA being installed, turn off the phone tunnel and stop Windows capture. Continue with the tested emulator route from step 2. The error does not by itself prove certificate pinning. There is no ordinary phone setting that forces an arbitrary app to accept a user CA.

The original project's Safari, iOS profile and Full Trust instructions do not apply to Android. For this Xiaomi's verified app version, the emulator system-store method solved the capture problem.

## 13. Troubleshooting

| Symptom | Check / action |
| --- | --- |
| `INSTALL_FAILED_OLDER_SDK` | Read the minimum API in the error. The tested app required 32; the capture image is 33. A newer app may require a reviewed image/certificate procedure. |
| `INSTALL_FAILED_NO_MATCHING_ABIS` | Use the complete x86_64 package set from the Play emulator. Recheck libraries before installing; the Xiaomi copy was ARM64-only. |
| `adbd cannot run as root in production builds` | The capture device has a production image, often a renamed Play device. Keep the Play source and create a separate Google APIs capture AVD. |
| More than one emulator / wrong device | Close the other emulator. Run the name check for the expected AVD. |
| `$adbPath`, `$workDir` or `Confirm-AirconDevice` is missing | Rerun step 5's initialization in the current PowerShell window. |
| Sent traffic but zero received / no handshake | Recheck Endpoint, current PC address, UDP listener, firewall and LAN isolation before certificates. A VPN switch alone is not a connection test. |
| Firewall says configured but connection fails | Rerun button ② after selecting/preparing the current address. The program can retain an earlier success marker. |
| No UDP listener | In administrator PowerShell, `Get-NetUDPEndpoint -LocalPort 51820` should show the selected address while the engine runs. Resolve startup/port errors first. |
| `http://mitm.it` says traffic is not going through mitmproxy | Verify the running engine and current imported tunnel; reconnect and retry in a fresh browser tab. |
| App certificate error in the emulator | Confirm the writable-system launch, reinstall the current CA and compare its bytes after reboot. A certificate left only in user credentials is insufficient for this tested app. |
| Room mismatch | Check your official app account and saved wall QR/device number. Resolve identity before control. |
| Authorization rejected | Check official app login and permissions; renew the token if needed. A permission/balance/network problem is not automatically token expiry. |
| No internet after token success | Disable the emulator/phone's WireGuard tunnel after the capture engine stops. |

Verification record: the successful workflow used two API 33 x86_64 AVDs, Play-delivered app packages, a system CA verified after reboot, and WireGuard. Token storage, a fresh read-only room-identity/status query, capture shutdown and tunnel shutdown were verified on 3 November 2026. No real token, room number or account email is included in these guides.
