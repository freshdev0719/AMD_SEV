import SwiftUI

struct RankingView: View {
    @AppStorage(SettingsKey.serverURL) private var serverURL = APIClient.defaultURL
    @State private var metric: Metric = .composite
    @State private var response: RankingResponse?
    @State private var errorMessage: String?
    @State private var isLoading = false

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Picker("기준", selection: $metric) {
                        ForEach(Metric.allCases) { Text($0.title).tag($0) }
                    }
                    .pickerStyle(.segmented)
                } footer: {
                    Text(metric.explanation)
                }

                if let response, !response.items.isEmpty {
                    Section {
                        ForEach(Array(response.items.enumerated()), id: \.element.id) { index, item in
                            NavigationLink(value: ComplexRoute(id: item.complexId, name: item.name)) {
                                RankingRow(rank: index + 1, item: item, metric: response.metric)
                            }
                        }
                    } header: {
                        Text("기준일 \(Format.date(response.asOf)) · 최근 \(response.windowDays)일")
                    }
                }
            }
            .overlay { overlay }
            .navigationTitle("분당 실거래 TOP 10")
            .navigationDestination(for: ComplexRoute.self) { ComplexDetailView(route: $0) }
            .task(id: "\(metric.rawValue)|\(serverURL)") { await load() }
            .refreshable { await load() }
        }
    }

    @ViewBuilder private var overlay: some View {
        if let errorMessage, response == nil {
            ContentUnavailableView {
                Label("불러오지 못했습니다", systemImage: "wifi.exclamationmark")
            } description: {
                Text(errorMessage)
            } actions: {
                Button("다시 시도") { Task { await load() } }
            }
        } else if isLoading, response == nil {
            ProgressView()
        } else if let response, response.items.isEmpty {
            ContentUnavailableView(
                "데이터가 없습니다",
                systemImage: "tray",
                description: Text("서버에서 collect.py로 수집을 먼저 실행하세요.")
            )
        }
    }

    private func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            response = try await APIClient(serverURL).rankings(metric: metric)
            errorMessage = nil
        } catch let error where error.isCancellation {
            // 기준을 빠르게 바꾸면 이전 요청이 취소된다.
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

private struct RankingRow: View {
    let rank: Int
    let item: RankingItem
    let metric: Metric

    var body: some View {
        HStack(spacing: 12) {
            Text("\(rank)")
                .font(.headline.monospacedDigit())
                .frame(width: 26)
                .foregroundStyle(rank <= 3 ? Color.accentColor : .secondary)

            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Text(item.name).font(.headline).lineLimit(1)
                    if item.newHighs > 0 {
                        TagLabel(text: "신고가 \(item.newHighs)")
                    }
                }
                Text(subtitle)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }

            Spacer(minLength: 8)

            VStack(alignment: .trailing, spacing: 4) {
                Text(primaryValue)
                    .font(.headline.monospacedDigit())
                    .foregroundStyle(primaryColor)
                Text(secondaryValue)
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 2)
    }

    private var subtitle: String {
        var parts = [item.dong]
        if let year = item.buildYear { parts.append("\(year)년") }
        if let price = item.latestPrice, let area = item.latestArea {
            parts.append("최근 \(Format.price(price)) (\(Int(area.rounded()))㎡)")
        }
        return parts.joined(separator: " · ")
    }

    private var primaryValue: String {
        switch metric {
        case .composite: item.score.map { "\(Int(($0 * 100).rounded()))점" } ?? "-"
        case .volume: "\(item.volume)건"
        case .growth: Format.percent(item.growth)
        case .volumeChange: Format.percent(item.volumeChange)
        }
    }

    private var primaryColor: Color {
        switch metric {
        case .growth: Format.changeColor(item.growth)
        case .volumeChange: Format.changeColor(item.volumeChange)
        default: .primary
        }
    }

    private var secondaryValue: String {
        switch metric {
        case .composite: "\(item.volume)건 · \(Format.percent(item.growth))"
        case .volume: "가격 \(Format.percent(item.growth))"
        case .growth: "거래 \(item.volume)건"
        case .volumeChange: "\(item.priorVolume)건 → \(item.volume)건"
        }
    }
}
