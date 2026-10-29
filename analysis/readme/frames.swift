// README 用: 動画から一定間隔でフレームを JPEG に書き出す(ffmpeg なしで AVFoundation を使う)
//   swift analysis/readme/frames.swift <in.mov> <outdir> <t0_s> <t1_s> <fps> <max_px>
import AVFoundation
import AppKit

let a = CommandLine.arguments
let url = URL(fileURLWithPath: a[1]), out = a[2]
let t0 = Double(a[3])!, t1 = Double(a[4])!, fps = Double(a[5])!, maxPx = Double(a[6])!
try? FileManager.default.createDirectory(atPath: out, withIntermediateDirectories: true)
let asset = AVURLAsset(url: url)
let gen = AVAssetImageGenerator(asset: asset)
gen.appliesPreferredTrackTransform = true          // iPhone の縦横を正しく
gen.requestedTimeToleranceBefore = .zero
gen.requestedTimeToleranceAfter = .zero
gen.maximumSize = CGSize(width: maxPx, height: maxPx)
var k = 0
var t = t0
while t < t1 {
    let time = CMTime(seconds: t, preferredTimescale: 600)
    if let cg = try? gen.copyCGImage(at: time, actualTime: nil) {
        let rep = NSBitmapImageRep(cgImage: cg)
        let data = rep.representation(using: .jpeg, properties: [.compressionFactor: 0.9])!
        try! data.write(to: URL(fileURLWithPath: String(format: "%@/f%04d.jpg", out, k)))
        k += 1
    }
    t += 1.0 / fps
}
print("frames", k, "duration", CMTimeGetSeconds(asset.duration))
