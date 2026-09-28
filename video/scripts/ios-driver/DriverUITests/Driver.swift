import XCTest
import ObjectiveC

/// XCUITest attend que l'app soit « au repos » avant/après chaque geste en prenant des instantanés
/// d'accessibilité : ça charge le fil principal et fait caler les animations filmées (gels de
/// 150-300 ms mesurés à l'ouverture de la sidebar). On neutralise cette attente.
private func disableQuiescenceWait() {
    guard let cls = NSClassFromString("XCUIApplicationProcess") else { return }
    for name in ["waitForQuiescenceIncludingAnimationsIdle:", "waitForQuiescenceIncludingAnimationsIdle:isPreEvent:"] {
        let sel = NSSelectorFromString(name)
        guard let m = class_getInstanceMethod(cls, sel) else { continue }
        if name.hasSuffix("isPreEvent:") {
            let block: @convention(block) (AnyObject, Bool, Bool) -> Void = { _, _, _ in }
            method_setImplementation(m, imp_implementationWithBlock(block))
        } else {
            let block: @convention(block) (AnyObject, Bool) -> Void = { _, _ in }
            method_setImplementation(m, imp_implementationWithBlock(block))
        }
    }
}

/// Pilote l'app via un fichier de commandes : `<id>\n<cmd>\t<arg>…` dans $PV_IO_DIR/cmd.txt,
/// réponse `<id>\n<résultat>` dans resp.txt. Variables passées par xcodebuild avec le préfixe
/// TEST_RUNNER_ (TEST_RUNNER_PV_IO_DIR, TEST_RUNNER_PV_BUNDLE_ID).
final class Driver: XCTestCase {
    func testDrive() throws {
        let env = ProcessInfo.processInfo.environment
        let dir = env["PV_IO_DIR"] ?? "/tmp/video-driver-io"
        guard let bundle = env["PV_BUNDLE_ID"] else { XCTFail("TEST_RUNNER_PV_BUNDLE_ID manquant (bundle id de l'app à piloter)"); return }
        let app = XCUIApplication(bundleIdentifier: bundle)
        continueAfterFailure = true
        if env["PV_KEEP_QUIESCENCE"] == nil { disableQuiescenceWait() }
        app.activate()
        var last = ""
        let fm = FileManager.default
        while true {
            guard let data = fm.contents(atPath: dir + "/cmd.txt"), let raw = String(data: data, encoding: .utf8),
                  let nl = raw.firstIndex(of: "\n") else { usleep(150_000); continue }
            let id = String(raw[..<nl]); let body = String(raw[raw.index(after: nl)...])
            if id == last { usleep(150_000); continue }
            last = id
            var out = "ok"
            let parts = body.components(separatedBy: "\t")
            let origin = app.coordinate(withNormalizedOffset: .zero)
            func pt(_ x: String, _ y: String) -> XCUICoordinate { origin.withOffset(CGVector(dx: Double(x)!, dy: Double(y)!)) }
            switch parts[0] {
            case "tap": pt(parts[1], parts[2]).tap()
            case "long": pt(parts[1], parts[2]).press(forDuration: Double(parts[3]) ?? 1)
            case "swipe":
                pt(parts[1], parts[2]).press(forDuration: 0.05, thenDragTo: pt(parts[3], parts[4]), withVelocity: .default, thenHoldForDuration: 0.1)
            case "slowswipe":
                pt(parts[1], parts[2]).press(forDuration: 0.05, thenDragTo: pt(parts[3], parts[4]), withVelocity: .slow, thenHoldForDuration: 0.2)
            case "type":
                guard app.keyboards.count > 0 else { out = "nokeyboard"; break }
                app.typeText(parts[1].replacingOccurrences(of: "\\n", with: "\n"))
            case "label":
                let e = app.descendants(matching: .any).matching(NSPredicate(format: "label ==[c] %@ OR identifier == %@", parts[1], parts[1])).firstMatch
                if e.waitForExistence(timeout: 3) { e.tap() } else { out = "notfound" }
            case "sb":
                let b = XCUIApplication(bundleIdentifier: "com.apple.springboard").buttons[parts[1]]
                if b.waitForExistence(timeout: 3) { b.tap() } else { out = "notfound" }
            case "tree": out = app.debugDescription
            case "activate": app.activate()
            case "quit": try? (id + "\nbye").write(toFile: dir + "/resp.txt", atomically: true, encoding: .utf8); return
            default: out = "unknown"
            }
            try? (id + "\n" + out).write(toFile: dir + "/resp.txt", atomically: true, encoding: .utf8)
        }
    }
}
