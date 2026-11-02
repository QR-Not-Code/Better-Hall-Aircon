# Renew an expired Hall Aircon token using the existing Android setup

Use this guide after completing the [first-time Android setup](/C:/Users/User/Desktop/python/personal/Better-Hall-Aircon/ANDROID_EMULATOR_SETUP.md). It is self-contained for routine renewal: all PowerShell initialization, certificate checks and capture steps are included here.

The normal renewal uses **HallAircon_API33**, the **Google APIs** capture emulator. **HallAircon_Play_API33** is needed again only if the app must be obtained or updated through Play Store.

The desktop program does not currently automate token refresh. Renewal obtains fresh authorization through your own official Hall Aircon app session and saves it after room validation. The workflow below follows the setup verified on **3 November 2026**; app updates may introduce new requirements.

## What to keep and what to recheck

| Item | During routine renewal |
| --- | --- |
| Both virtual devices | Keep them. Run only the capture device unless an app update is needed. |
| Hall Aircon and WireGuard installations | Normally remain installed; reinstallation is unnecessary if the checks below pass. |
| Capture emulator login | May persist, but the official app can require sign-in again. |
| `%LOCALAPPDATA%\HallAirconStudio` | Preserve the encrypted vault, saved room, capture CA, tunnel keys and helper files. |
| System capture CA inside the emulator | Check every session. Closing an emulator launched with `-writable-system` can discard system changes. Reinstall if missing or different. |
| PC IPv4 / tunnel Endpoint / firewall | Recheck. The PC address may have changed since the last capture. |

The system image, not its display name, determines root access. The capture AVD must use **Android 13 / API 33 / Google APIs / x86_64**. A renamed Google Play device still cannot run ordinary `adb root`. [Android image documentation](https://developer.android.com/studio/run/managing-avds)

## 1. Confirm renewal is needed and pause existing work

1. In Better Hall Aircon, try **Refresh status**. A rejected authorization can indicate expiry or revocation; network failures, room mismatch, missing permission or balance problems need their own checks.
2. Check that your official Hall Aircon account is usable and still associated with your own room.
3. Stop any running Better Hall Aircon scripts while replacing authorization. Stop any old capture session.
4. If an emulator or phone tunnel is currently enabled, turn it off before preparing the new session.

A JWT expiry timestamp is only a hint: the server can reject authorization earlier. Follow actual validation results. Keep the Windows program's saved account and room while renewing; use the **official app in the emulator** for sign-out/sign-in when needed.

## 2. Prepare the Windows capture for the current network

In **Better Hall Aircon → Connection/setup → Get Token**:

1. Check that the saved room device number is still your own room. Restore it from the wall QR/device number if missing.
2. Stop capture before changing connection settings.
3. Refresh addresses and select the PC's current physical Wi-Fi or Ethernet IPv4 address. Use `ipconfig` if uncertain.
4. Click **① Prepare connection QR code**. This refreshes `phone.conf` and ensures the current capture CA exists.
5. Click **② Configure firewall** and approve Windows' administrator prompt. Reapply it when the address changes, even if an old configured message remains.
6. Select **Get authorization / stop automatically**, rather than learning mode. Leave the engine stopped until step 7.

`192.168.0.100` was the address used during the successful setup. Use today's address, not that example or an unrelated ZeroTier/VPN address. The server uses **UDP 51820**. Emulator capture needs no Windows hotspot.

## 3. Start the capture emulator with a writable system

Close the Play emulator. If the capture emulator is already running from the correct writable-system launch, keep that session. Otherwise, open **PowerShell Window A** and run:

```powershell
$emulatorPath = Join-Path $env:LOCALAPPDATA 'Android\Sdk\emulator\emulator.exe'
& $emulatorPath -avd HallAircon_API33 -writable-system -no-snapshot
```

Leave Window A open. Wait for the Android home screen. Open emulator WireGuard and ensure its tunnel is **off** during preparation.

If the emulator was started normally through Device Manager and the certificate is missing, close that session and relaunch using this command. Google's [writable-system documentation](https://developer.android.com/studio/run/emulator-commandline) explains that the system copy is temporary; prior certificate installation alone is not sufficient proof for a new session.

## 4. Initialize a fresh PowerShell working window

Open **PowerShell Window B** and paste the whole block below. All subsequent command blocks run in Window B. If it is closed, rerun this initialization in the new window before continuing.

The default SDK path is used below; adjust `$airconSdk` if your SDK is elsewhere. If OpenSSL is missing, use the installed Git for Windows location or reinstall [Git for Windows](https://git-scm.com/install/windows).

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
function Confirm-AirconCapture {
    $avdLines = @(& $adbPath -e emu avd name)
    if ($LASTEXITCODE -ne 0 -or 'HallAircon_API33' -notin @($avdLines | ForEach-Object { $_.Trim() })) {
        throw 'Run only HallAircon_API33 and wait for its home screen.'
    }
    $bootLines = @(& $adbPath -e shell getprop sys.boot_completed)
    $sdkLines = @(& $adbPath -e shell getprop ro.build.version.sdk)
    $debugLines = @(& $adbPath -e shell getprop ro.debuggable)
    if (($bootLines -join '').Trim() -ne '1') { throw 'Android is still booting. Wait and retry.' }
    if (($sdkLines -join '').Trim() -ne '33') { throw 'This guide expects the existing API 33 capture image.' }
    if (($debugLines -join '').Trim() -ne '1') { throw 'This is a production image. Use the separate Google APIs capture device.' }
}
Confirm-AirconCapture
$hallPackages = @(& $adbPath -e shell pm path sg.daikin.ntu.ntu_mobile)
$wgPackages = @(& $adbPath -e shell pm path com.wireguard.android)
if (-not ($hallPackages -match '^package:')) { throw 'Hall Aircon is missing. Restore it using the first-time guide, steps 6–7.' }
if (-not ($wgPackages -match '^package:')) { throw 'WireGuard is missing. Restore it using the first-time guide, step 9.' }
'Capture device and both apps are present.'
```

**Checkpoint:** the final message appears. These checks do not read the saved token or account data. If the device or app is missing, repair that part with the first-time guide before renewing.

## 5. Check or reinstall the current system CA

### 5a. Calculate the current CA filename and compare the installed bytes

Run in Window B after preparing the connection in step 2:

```powershell
Confirm-AirconCapture
$caCert = Join-Path $captureDir 'mitmproxy-ca-cert.cer'
if (-not (Test-Path -LiteralPath $caCert)) { throw 'Prepare the connection in Better Hall Aircon first.' }
$hashOutput = @(& $opensslPath x509 -in $caCert -noout -subject_hash_old)
if ($LASTEXITCODE -ne 0) { throw 'Could not read the current public capture CA.' }
$caHash = ($hashOutput | Select-Object -First 1).Trim()
if ($caHash -notmatch '^[0-9a-fA-F]{8}$') { throw 'Unexpected CA hash.' }
$namedCert = Join-Path $workDir ($caHash + '.0')
Copy-Item -LiteralPath $caCert -Destination $namedCert -Force
$androidCert = '/system/etc/security/cacerts/' + $caHash + '.0'
$probeCert = Join-Path $workDir ('ca-check-' + [guid]::NewGuid().ToString('N') + '.cer')
$probeOutput = @(& $adbPath -e pull $androidCert $probeCert 2>&1)
$probeExit = $LASTEXITCODE
$caMatches = $false
if ($probeExit -eq 0 -and (Test-Path -LiteralPath $probeCert)) {
    $caMatches = (Get-FileHash -LiteralPath $probeCert -Algorithm SHA256).Hash -eq (Get-FileHash -LiteralPath $caCert -Algorithm SHA256).Hash
}
Write-Output ('Current system CA matches: ' + $caMatches)
```

- If the result is **True**, skip 5b and continue at **step 6**.
- If it is **False**, the system CA is missing or different. Complete **5b**.

The certificate's name/subject hash can stay the same after a CA is regenerated. Comparing its full file hash prevents accidentally reusing a different certificate. [OpenSSL subject hash](https://docs.openssl.org/3.0/man1/openssl-x509/)

### 5b. Install the system CA when needed

Keep the variables calculated in 5a. Run:

```powershell
Confirm-AirconCapture
& $adbPath -e root
if ($LASTEXITCODE -ne 0) { throw 'Root access failed.' }
& $adbPath -e wait-for-device
& $adbPath -e disable-verity
if ($LASTEXITCODE -ne 0) { throw 'Could not prepare the system for writing.' }
& $adbPath -e reboot
```

Wait for the emulator home screen, then run:

```powershell
Confirm-AirconCapture
& $adbPath -e root
& $adbPath -e wait-for-device
& $adbPath -e remount
if ($LASTEXITCODE -ne 0) { throw 'Remount failed. Resolve it before copying the CA.' }
```

If remount requests a further reboot, run the block below, wait for the home screen, and repeat the preceding root/remount block. Continue only after remount succeeds without a further reboot request.

```powershell
& $adbPath -e reboot
```

Copy the CA, set its file properties, and restart Android:

```powershell
& $adbPath -e push $namedCert $androidCert
if ($LASTEXITCODE -ne 0) { throw 'System certificate copy failed.' }
& $adbPath -e shell chmod 644 $androidCert
if ($LASTEXITCODE -ne 0) { throw 'Certificate permissions failed.' }
& $adbPath -e shell chown 0:0 $androidCert
if ($LASTEXITCODE -ne 0) { throw 'Certificate ownership failed.' }
& $adbPath -e shell restorecon $androidCert
if ($LASTEXITCODE -ne 0) { throw 'Certificate file context failed.' }
& $adbPath -e reboot
```

Wait for the home screen, then verify the installed copy:

```powershell
Confirm-AirconCapture
$verifiedCert = Join-Path $workDir ('verified-ca-' + [guid]::NewGuid().ToString('N') + '.cer')
& $adbPath -e pull $androidCert $verifiedCert
if ($LASTEXITCODE -ne 0) { throw 'System CA missing after reboot.' }
if ((Get-FileHash -LiteralPath $verifiedCert -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath $caCert -Algorithm SHA256).Hash) {
    throw 'System CA still differs from the current capture CA.'
}
'Current system CA verified after reboot.'
```

This is the root/remount and CA placement procedure used in the successful setup. References: [Android writable overlays](https://android.googlesource.com/platform/system/core/+/refs/heads/main/fs_mgr/README.overlayfs.md), [mitmproxy Android system CA](https://docs.mitmproxy.org/stable/howto/install-system-trusted-ca-android/).

## 6. Refresh the emulator's tunnel configuration

Keep the emulator's WireGuard tunnel off while updating it. In Window B:

```powershell
Confirm-AirconCapture
$phoneProfile = Join-Path $captureDir 'phone.conf'
if (-not (Test-Path -LiteralPath $phoneProfile)) { throw 'Prepare the Windows connection in step 2 first.' }
Get-Content -LiteralPath $phoneProfile | Select-String -Pattern '^Endpoint\s*='
& $adbPath -e push $phoneProfile /sdcard/Download/hall-aircon.conf
if ($LASTEXITCODE -ne 0) { throw 'Tunnel configuration transfer failed.' }
```

In emulator **WireGuard**:

1. With it disabled, remove the previous **Hall Aircon capture tunnel** so importing the same name does not create a duplicate/conflict.
2. Choose **+ → Import from file or archive → Downloads → hall-aircon.conf**.
3. Check the Endpoint against the current PC address selected in step 2, with port **51820**. Preserve the generated keys, DNS and routing settings.

Refreshing the file covers a changed PC address or regenerated tunnel keys. Keep the physical Xiaomi's copy of the capture tunnel disabled during emulator capture.

## 7. Start capture and verify the connection

1. In Better Hall Aircon on Windows, select **Get authorization / stop automatically** and click **③ Start and wait for authorization**.
2. Wait for **Capture engine ready**.
3. Enable the tunnel in emulator WireGuard and accept any Android VPN prompt.
4. Check for a recent handshake and traffic received as well as sent. Windows should report a recent captured connection.
5. In the emulator browser, enter **http://mitm.it**. Expect the mitmproxy certificate page. The system CA has already been checked; no iOS profile or Full Trust setting is involved.

If traffic never reaches the engine, fix that before investigating app login. The green VPN switch alone is insufficient evidence of a working tunnel.

## 8. Make the official app obtain fresh authorization

1. Open **Hall Aircon in HallAircon_API33** and refresh your room's status. The official app may renew its session automatically or ask you to sign in.
2. If prompted, sign into your own account and complete normal SSO/MFA steps.
3. If Better Hall Aircon keeps reporting rejected authorization, or the official app keeps using an expired session, use the official app's **Sign out / Log out**, then sign back in while capture is running. Refresh status again after login.
4. If necessary, use Android **Settings → Apps → Hall Aircon → Force stop**, reopen it and repeat the normal sign-in/refresh. Use ordinary app sign-out before considering any app-data reset.
5. Confirm that the official app is showing your own bound room. Correct account/room mismatches before accepting the capture result.

Use the official app's sign-out action for fresh login. Better Hall Aircon's **Exit current account** removes its locally saved room/authorization and is unnecessary for routine renewal.

The new token must be generated by the server. Recopying an expired saved token does not renew it. Capture can initially see an old token before sign-in completes; keep the session running until a fresh token passes validation.

## 9. Confirm the replacement token and finish

1. Wait for Better Hall Aircon's **Token acquired / aircon connected** result with the correct room. The program checks `/me` and saves successful authorization to its Windows-encrypted vault.
2. Confirm capture has stopped. If it remains running, stop it manually after the successful result.
3. **Turn off the emulator's WireGuard tunnel** after capture stops.
4. Enter the Windows control panel and click **Refresh status**. A successful response for the configured room confirms the saved authorization works. Switching the aircon on/off is unnecessary for this check.
5. Resume your scripts only after this validation succeeds. You can close the emulator; local automation still requires Better Hall Aircon and the PC to remain running.

If you need the token elsewhere, use **Copy complete token** in the result window or the program's saved-token view. The normal capture route already saves it; a manual import is unnecessary after successful capture.

## 10. Troubleshooting and repair

| Problem | Action |
| --- | --- |
| Zero received traffic / no handshake | Check today's Endpoint, imported configuration, engine readiness, UDP 51820 listener and firewall. |
| Capture engine exited | Resolve startup/port conflicts and restart it before enabling the tunnel. |
| Browser says traffic is not going through mitmproxy | Check that this capture emulator's current tunnel is enabled and connected to the running engine; retry in a fresh tab. |
| `CERTIFICATE_VERIFY_FAILED` | Repeat step 5 using the current Windows CA, with the writable-system launch. Check bytes after reboot, rather than only the CA's name. |
| Root unavailable | Confirm the AVD uses Google APIs rather than Google Play; renaming does not change images. |
| App absent or incompatible after an update | Use the first-time guide's Play download/copy/ABI checks. Obtain a complete matching set and reinstall it on the capture AVD. Recheck minimum API before changing Android images. |
| `INSTALL_FAILED_NO_MATCHING_ABIS` | Use the x86_64 packages from the Play emulator, not the ARM64 phone copy. |
| Room mismatch | Check your login and saved room QR/device number; this is not solved by bypassing validation. |
| Expired token keeps appearing | Sign out/back in within the official emulator app while capture runs, then refresh status. |
| Only an expiry timestamp is shown | Verify by refreshing status. The JWT timestamp is not a promise that the server will accept authorization until then. |
| No internet after capture | Turn off WireGuard once the engine stops. |
| PowerShell variables/functions are missing | Rerun step 4 in the current Window B, then rerun step 5a before any certificate-install commands. |

For an app update, run the Play emulator separately, update Hall Aircon in Play Store, then follow the first-time guide's steps 6–7 to copy the entire matching package set and install it with replacement enabled. Return here at step 5. Keep the original capture CA/settings unless they actually need replacement.

## 11. If your original capture worked directly on a physical Android phone

This optional renewal applies only to an app/phone that previously accepted the user-installed CA. It was not the successful route for the tested Xiaomi app version.

1. Stop the phone tunnel and old Windows capture. Check the saved room and today's PC address in Better Hall Aircon.
2. Prepare a fresh connection QR with **①** and reconfigure the firewall with **②**, approving Windows' prompt.
3. Replace the phone's Hall Aircon WireGuard profile with the new QR configuration. Start Windows capture with **③**, then enable the phone tunnel.
4. Verify the handshake and open **http://mitm.it**. If the capture CA was regenerated, download the current Android CA and install it through **Settings → Install a certificate → CA certificate**.
5. Open the official phone app, refresh status, and sign out/back in if needed to obtain a fresh session.
6. After the Windows program captures and room-validates the new token, stop capture, disable the phone tunnel and refresh the Windows control panel.
7. If the app rejects the CA, switch to the tested emulator procedure above. Reinstalling a user CA cannot force an app to trust it. [Android certificate policy](https://developer.android.com/privacy-and-security/security-config)

This guide contains no real token, account email, room number or private key. It describes renewal using the setup verified on 3 November 2026; a future expiry has not been artificially induced or tested.
