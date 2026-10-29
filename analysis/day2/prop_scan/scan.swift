// scan.swift — RealityKit Object Capture: image folder -> USDZ, then ModelIO -> OBJ
import Foundation
import RealityKit
import ModelIO

let args = CommandLine.arguments
let input = URL(fileURLWithPath: args[1], isDirectory: true)
let outUSDZ = URL(fileURLWithPath: args[2])
let detail: PhotogrammetrySession.Request.Detail = (args.count > 3 && args[3] == "full") ? .full : .medium

var config = PhotogrammetrySession.Configuration()
config.featureSensitivity = .high
config.sampleOrdering = .sequential
config.isObjectMaskingEnabled = false

let session = try PhotogrammetrySession(input: input, configuration: config)
let done = DispatchSemaphore(value: 0)
Task {
    do {
        for try await out in session.outputs {
            switch out {
            case .requestProgress(_, let f): print(String(format: "progress %.0f%%", f * 100)); fflush(stdout)
            case .requestComplete(_, let r): print("complete:", r)
            case .requestError(_, let e): print("error:", e)
            case .processingComplete: done.signal()
            case .invalidSample(let id, let reason): print("invalid sample", id, reason)
            case .skippedSample(let id): print("skipped sample", id)
            case .automaticDownsampling: print("automatic downsampling")
            default: break
            }
        }
    } catch { print("output error:", error); done.signal() }
}
try session.process(requests: [.modelFile(url: outUSDZ, detail: detail)])
done.wait()

// USDZ -> OBJ (+MTL, textures) for three.js
let asset = MDLAsset(url: outUSDZ)
asset.loadTextures()
let objURL = outUSDZ.deletingPathExtension().appendingPathExtension("obj")
do { try asset.export(to: objURL); print("wrote", objURL.path) } catch { print("obj export failed:", error) }
