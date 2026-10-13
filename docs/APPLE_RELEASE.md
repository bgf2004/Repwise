# Repwise: Apple App Store release plan

Prepared September 24, 2026. This is a plan for the existing laptop prototype; no iOS build has been created or submitted.

## Run the existing app on this Windows laptop

1. Open your local `Repwise` project folder in File Explorer after completing the README setup steps.
2. Double-click **Start Repwise.cmd**. Keep the window open while using the app.
3. Open **http://127.0.0.1:8765** in Chrome or Edge. If the browser opens before the server finishes starting, refresh it.
4. Choose an exercise, enter the weight and target reps, and start a set. Enable the camera explicitly when you want camera tracking; manual logging also works.
5. Save the set to retain it in workout history. Press Ctrl+C in the server window when finished.

After the initial setup, there is no need to run setup each time. If the app is already running at that address, use the existing instance instead of launching another. `setup.ps1` is for first installation or updating dependencies/build assets; see the project README for setup on another Windows computer.

Workout records are stored in `data/workouts.sqlite3`. Back up the database while the server is stopped. Camera frames are processed locally and are not saved as workout videos. This localhost address belongs to this computer; it is not a published website or an iPhone app.

## Recommended first iPhone release

Reuse the React/TypeScript interface with Capacitor, which packages a web application inside a native iOS app. I recommend an initial version that stores workouts and computes rest suggestions on the phone, with no account required. This avoids a server subscription and lets the main workout flow work without internet access. It requires porting the current Python storage/recommendation layer and testing equivalent behavior; adding a wrapper alone is insufficient. [Capacitor documentation](https://capacitorjs.com/docs)

An alternative is to keep FastAPI on an HTTPS server and add authentication, per-user access controls, backups, and a synchronization/offline strategy. That preserves more Python code and supports future multi-device access, but adds hosting and account-management work. These are engineering choices, not claims that Apple mandates a particular framework or backend.

The existing camera pipeline must be tested on real iPhones. Browser success on Windows does not establish iOS camera, WebAssembly, GPU, or battery behavior. Use an iOS-native pose implementation if the web pipeline proves unsuitable on the target phones.

## Steps to publication

1. **Build the mobile data layer and iOS package.** Bundle the interface/model assets, implement persistent phone storage, and remove the dependency on the laptop's localhost server. Preserve manual corrections and export. Add a clear way to delete local workout data.
2. **Test real workout sessions on an iPhone.** Verify camera permission denial, squat/curl counting, phase timing, camera interruptions, rotations, locked-screen rest timing, saving/reopening a workout, and operation without a network connection. Collect consented, separately labeled exercise clips before claiming recognition accuracy.
3. **Use a Mac with Xcode for the iOS build.** Windows can still be used to develop shared web code. A Mac/cloud Mac build environment is needed for packaging and signing iOS; access to a real iPhone is valuable for camera testing. Check current Capacitor/Xcode compatibility when starting the build. [Capacitor environment requirements](https://capacitorjs.com/docs/getting-started/environment-setup)
4. **Enroll for distribution.** Apple's Developer Program currently costs **US$99 per year**, or local pricing where available. A free Apple developer account supports limited personal-device development; App Store distribution and TestFlight use the paid program. [Apple Developer Program](https://developer.apple.com/programs/)
5. **Prepare the app's public information.** Supply an icon, screenshots, description, support information, privacy policy, and accurate App Privacy disclosures. Describe camera use clearly, review third-party dependencies, and disclose the data practices of the final mobile build. If accounts are added later, include in-app account deletion. [App privacy](https://developer.apple.com/help/app-store-connect/manage-app-information/manage-app-privacy), [App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/)
6. **Upload a signed build, beta test, and submit for review.** Create the app record in App Store Connect, test through TestFlight, fix problems found by testers, and submit the selected build and listing for review. Explain how reviewers can exercise the camera and manual workout flows. Publication follows approval; approval is not guaranteed by using any particular framework. [App Store Connect workflow](https://developer.apple.com/help/app-store-connect/get-started/app-store-connect-workflow), [TestFlight](https://developer.apple.com/help/app-store-connect/test-a-beta-version/testflight-overview/)

## Claims to use carefully

The implemented rep-speed measure is movement-phase duration, not calibrated bar velocity. Rest suggestions summarize associations in comparable historical sets; they have not been proven to identify an optimal rest period or improve strength. Automated software tests and laptop API benchmarks do not establish real-person rep-count accuracy, iPhone frame rate, battery life, or health outcomes. Keep these distinctions in the store listing and resume.
