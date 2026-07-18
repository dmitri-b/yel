import AVFoundation
import Foundation
import Speech

private enum NativeASRError: Error, CustomStringConvertible {
  case invalidArguments(String)
  case unavailable
  case unsupportedLocale(String)
  case invalidAudio(String)

  var description: String {
    switch self {
    case .invalidArguments(let message):
      return message
    case .unavailable:
      return "SpeechTranscriber is unavailable on this Mac"
    case .unsupportedLocale(let locale):
      return "SpeechTranscriber does not support locale \(locale)"
    case .invalidAudio(let message):
      return message
    }
  }
}

private struct Options {
  let sampleRate: Double
  let localeIdentifier: String

  static func parse(_ arguments: [String]) throws -> Options {
    var sampleRate = 16_000.0
    var localeIdentifier = "en-US"
    var index = 1

    while index < arguments.count {
      switch arguments[index] {
      case "--sample-rate":
        guard index + 1 < arguments.count,
          let value = Double(arguments[index + 1]),
          value > 0
        else {
          throw NativeASRError.invalidArguments("--sample-rate requires a positive number")
        }
        sampleRate = value
        index += 2
      case "--locale":
        guard index + 1 < arguments.count, !arguments[index + 1].isEmpty else {
          throw NativeASRError.invalidArguments("--locale requires a locale identifier")
        }
        localeIdentifier = arguments[index + 1]
        index += 2
      default:
        throw NativeASRError.invalidArguments("unknown argument: \(arguments[index])")
      }
    }

    return Options(sampleRate: sampleRate, localeIdentifier: localeIdentifier)
  }
}

@main
private struct YelSpeechTranscriber {
  static func main() async {
    do {
      let options = try Options.parse(CommandLine.arguments)
      let audio = FileHandle.standardInput.readDataToEndOfFile()
      let transcript = try await transcribe(audio, options: options)
      FileHandle.standardOutput.write(Data((transcript + "\n").utf8))
    } catch {
      FileHandle.standardError.write(Data("yel native ASR: \(error)\n".utf8))
      Foundation.exit(1)
    }
  }

  @available(macOS 26.0, *)
  private static func transcribe(_ data: Data, options: Options) async throws -> String {
    guard SpeechTranscriber.isAvailable else {
      throw NativeASRError.unavailable
    }
    if data.isEmpty {
      return ""
    }
    guard data.count.isMultiple(of: MemoryLayout<Int16>.size) else {
      throw NativeASRError.invalidAudio("stdin must contain raw little-endian Int16 PCM")
    }

    let requestedLocale = Locale(identifier: options.localeIdentifier)
    guard let locale = await SpeechTranscriber.supportedLocale(equivalentTo: requestedLocale)
    else {
      throw NativeASRError.unsupportedLocale(options.localeIdentifier)
    }

    let transcriber = SpeechTranscriber(locale: locale, preset: .transcription)
    guard
      let format = AVAudioFormat(
        commonFormat: .pcmFormatInt16,
        sampleRate: options.sampleRate,
        channels: 1,
        interleaved: false
      )
    else {
      throw NativeASRError.invalidAudio("could not create the PCM input format")
    }

    let analyzer = SpeechAnalyzer(modules: [transcriber])
    try await analyzer.prepareToAnalyze(in: format)

    let (inputs, continuation) = AsyncStream<AnalyzerInput>.makeStream()
    async let transcript = transcriber.results.reduce(into: "") { result, item in
      result += String(item.text.characters)
    }
    async let lastSample = analyzer.analyzeSequence(inputs)

    let bytesPerFrame = MemoryLayout<Int16>.size
    let totalFrames = data.count / bytesPerFrame
    let framesPerBuffer = 4_096

    try data.withUnsafeBytes { rawBytes in
      guard let source = rawBytes.baseAddress else {
        throw NativeASRError.invalidAudio("stdin contained no PCM samples")
      }
      var frameOffset = 0
      while frameOffset < totalFrames {
        let frameCount = min(framesPerBuffer, totalFrames - frameOffset)
        guard
          let buffer = AVAudioPCMBuffer(
            pcmFormat: format,
            frameCapacity: AVAudioFrameCount(frameCount)
          ), let channel = buffer.int16ChannelData?[0]
        else {
          throw NativeASRError.invalidAudio("could not allocate an audio buffer")
        }
        buffer.frameLength = AVAudioFrameCount(frameCount)
        memcpy(
          channel,
          source.advanced(by: frameOffset * bytesPerFrame),
          frameCount * bytesPerFrame
        )
        continuation.yield(AnalyzerInput(buffer: buffer))
        frameOffset += frameCount
      }
    }
    continuation.finish()

    if let lastSample = try await lastSample {
      try await analyzer.finalizeAndFinish(through: lastSample)
    } else {
      await analyzer.cancelAndFinishNow()
    }
    return try await transcript.trimmingCharacters(in: .whitespacesAndNewlines)
  }
}
