// Person matte + hand joints for every frame of a video, using Apple Vision (on device, no downloads).
// Build:  swiftc -O matte.swift -o matte
// Run:    ./matte <video.mp4> <outdir> [mode: person|subject] [first] [last]
// Writes: <outdir>/m_%05d.png (8 bit grey matte, native mask size) and <outdir>/hands.jsonl
import Foundation
import AVFoundation
import Vision
import CoreImage
import ImageIO
import UniformTypeIdentifiers

let args = CommandLine.arguments
guard args.count >= 3 else { print("usage: matte <video> <outdir> [person|subject] [first] [last]"); exit(2) }
let url = URL(fileURLWithPath: args[1])
let outDir = URL(fileURLWithPath: args[2])
let mode = args.count > 3 ? args[3] : "person"
let first = args.count > 4 ? Int(args[4])! : 0
let last = args.count > 5 ? Int(args[5])! : Int.max
try? FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)

func writeGray(_ pb: CVPixelBuffer, _ dst: URL) {
    CVPixelBufferLockBaseAddress(pb, .readOnly)
    defer { CVPixelBufferUnlockBaseAddress(pb, .readOnly) }
    let w = CVPixelBufferGetWidth(pb), h = CVPixelBufferGetHeight(pb), bpr = CVPixelBufferGetBytesPerRow(pb)
    let fmt = CVPixelBufferGetPixelFormatType(pb)
    var bytes = [UInt8](repeating: 0, count: w * h)
    let base = CVPixelBufferGetBaseAddress(pb)!
    if fmt == kCVPixelFormatType_OneComponent8 {
        for y in 0..<h {
            let row = base.advanced(by: y * bpr).assumingMemoryBound(to: UInt8.self)
            for x in 0..<w { bytes[y * w + x] = row[x] }
        }
    } else { // OneComponent32Float
        for y in 0..<h {
            let row = base.advanced(by: y * bpr).assumingMemoryBound(to: Float32.self)
            for x in 0..<w { bytes[y * w + x] = UInt8(max(0, min(255, row[x] * 255 + 0.5))) }
        }
    }
    let provider = CGDataProvider(data: Data(bytes) as CFData)!
    let cg = CGImage(width: w, height: h, bitsPerComponent: 8, bitsPerPixel: 8, bytesPerRow: w,
                     space: CGColorSpaceCreateDeviceGray(), bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.none.rawValue),
                     provider: provider, decode: nil, shouldInterpolate: false, intent: .defaultIntent)!
    let dest = CGImageDestinationCreateWithURL(dst as CFURL, UTType.png.identifier as CFString, 1, nil)!
    CGImageDestinationAddImage(dest, cg, nil)
    CGImageDestinationFinalize(dest)
}

let asset = AVURLAsset(url: url)
let track = try await asset.loadTracks(withMediaType: .video).first!
let reader = try AVAssetReader(asset: asset)
let output = AVAssetReaderTrackOutput(track: track, outputSettings: [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA])
output.alwaysCopiesSampleData = false
reader.add(output)
reader.startReading()

let seg = VNGeneratePersonSegmentationRequest()
seg.qualityLevel = .accurate
seg.outputPixelFormat = kCVPixelFormatType_OneComponent8
let hands = VNDetectHumanHandPoseRequest()
hands.maximumHandCount = 2
let seq = VNSequenceRequestHandler()

FileManager.default.createFile(atPath: outDir.appendingPathComponent("hands.jsonl").path, contents: nil)
let handsFile = try FileHandle(forWritingTo: outDir.appendingPathComponent("hands.jsonl"))
var idx = 0
let t0 = Date()
while let sb = output.copyNextSampleBuffer() {
    defer { idx += 1 }
    guard idx >= first, idx <= last, let pb = CMSampleBufferGetImageBuffer(sb) else { continue }
    let name = String(format: "m_%05d.png", idx)
    if mode == "subject" {
        let req = VNGenerateForegroundInstanceMaskRequest()
        let h = VNImageRequestHandler(cvPixelBuffer: pb, options: [:])
        try h.perform([req, hands])
        if let obs = req.results?.first {
            let m = try obs.generateScaledMaskForImage(forInstances: obs.allInstances, from: h)
            writeGray(m, outDir.appendingPathComponent(name))
        }
    } else {
        try seq.perform([seg, hands], on: pb)
        if let m = seg.results?.first?.pixelBuffer { writeGray(m, outDir.appendingPathComponent(name)) }
    }
    var list: [[String: Any]] = []
    for o in hands.results ?? [] {
        var pts: [String: [Double]] = [:]
        if let all = try? o.recognizedPoints(.all) {
            for (k, p) in all { pts[k.rawValue.rawValue] = [Double(p.location.x), Double(1 - p.location.y), Double(p.confidence)] }
        }
        list.append(["chirality": o.chirality == .left ? "left" : (o.chirality == .right ? "right" : "unknown"), "pts": pts])
    }
    let line = try JSONSerialization.data(withJSONObject: ["f": idx, "hands": list])
    handsFile.write(line); handsFile.write("\n".data(using: .utf8)!)
    if idx % 100 == 0 { print("frame \(idx)  \(String(format: "%.1f", Date().timeIntervalSince(t0)))s"); fflush(stdout) }
}
try handsFile.close()
print("done \(idx) frames in \(String(format: "%.1f", Date().timeIntervalSince(t0)))s")
