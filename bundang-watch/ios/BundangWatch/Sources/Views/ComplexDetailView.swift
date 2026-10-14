import Charts
import SwiftUI

struct ComplexDetailView: View {
    let route: ComplexRoute

    @AppStorage(SettingsKey.serverURL) private var serverURL = APIClient.defaultURL
    @Environment(FavoritesStore.self) private var favorites
    @State private var detail: ComplexDetail?
    @State private var errorMessage: String?
    @State private var selectedBucket: Int?  // nil = 전체 면적

    var body: some View {
        List {
            if let detail {
                header(detail.complex)
                if let stats = detail.stats {
                    statsSection(stats)
                }
                chartSection(detail.trades)
                tradesSection(detail.trades)
            }
        }
        .overlay {
            if let errorMessage, detail == nil {
                ContentUnavailableView("불러오지 못했습니다", systemImage: "wifi.exclamationmark", description: Text(errorMessage))
            } else if detail == nil {
                ProgressView()
            }
        }
        .navigationTitle(route.name)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button {
                    favorites.toggle(FavoriteComplex(id: route.id, name: route.name))
                } label: {
                    Image(systemName: favorites.contains(route.id) ? "star.fill" : "star")
                }
                .accessibilityLabel("관심 단지")
            }
        }
        .task { await load() }
        .refreshable { await load() }
    }

    // MARK: - Sections

    private func header(_ complex: ComplexInfo) -> some View {
        Section {
            VStack(alignment: .leading, spacing: 4) {
                Text(complex.name).font(.title2.bold())
                Text([complex.dong, complex.jibun, complex.buildYear.map { "\($0)년 준공" }]
                    .compactMap { $0 }
                    .joined(separator: " · "))
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private func statsSection(_ stats: RankingItem) -> some View {
        Section("최근 3개월 (1년 전 같은 기간 대비)") {
            LabeledContent("거래량", value: "\(stats.volume)건 (1년 전 \(stats.priorVolume)건)")
            LabeledContent("거래량 증가율") {
                Text(Format.percent(stats.volumeChange)).foregroundStyle(Format.changeColor(stats.volumeChange))
            }
            LabeledContent("가격 상승률") {
                Text(Format.percent(stats.growth)).foregroundStyle(Format.changeColor(stats.growth))
            }
            LabeledContent("신고가", value: "\(stats.newHighs)건")
            if let score = stats.score {
                LabeledContent("종합 점수", value: "\(Int((score * 100).rounded()))점")
            }
        }
    }

    private func chartSection(_ trades: [TradeItem]) -> some View {
        let buckets = Array(Set(trades.map(\.areaBucket))).sorted()
        let points = trades.filter { !$0.cancelled && (selectedBucket == nil || $0.areaBucket == selectedBucket) }

        return Section("가격 추이") {
            if buckets.count > 1 {
                Picker("면적", selection: $selectedBucket) {
                    Text("전체").tag(Int?.none)
                    ForEach(buckets, id: \.self) { Text("\($0)㎡").tag(Int?.some($0)) }
                }
            }
            if points.isEmpty {
                Text("표시할 거래가 없습니다.").foregroundStyle(.secondary)
            } else {
                Chart(points) { trade in
                    PointMark(
                        x: .value("계약일", trade.dealDate),
                        y: .value("가격(억)", Double(trade.price) / 10_000)
                    )
                    .foregroundStyle(by: .value("면적", "\(trade.areaBucket)㎡"))
                    .symbolSize(trade.isNewHigh ? 70 : 25)
                }
                .chartYAxisLabel("억원")
                .chartYScale(domain: .automatic(includesZero: false))
                .frame(height: 220)
                .padding(.vertical, 8)
            }
        }
    }

    private func tradesSection(_ trades: [TradeItem]) -> some View {
        Section("최근 거래") {
            ForEach(trades.prefix(50)) { trade in
                TradeRow(trade: trade)
            }
        }
    }

    private func load() async {
        do {
            detail = try await APIClient(serverURL).complex(id: route.id)
            errorMessage = nil
        } catch let error where error.isCancellation {
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

private struct TradeRow: View {
    let trade: TradeItem

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(Format.date(trade.dealDate)).font(.subheadline.monospacedDigit())
                Text("\(Format.area(trade.area)) · \(trade.floor.map { "\($0)층" } ?? "-")")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            if trade.cancelled {
                TagLabel(text: "해제", color: .gray)
            } else if trade.isDirectDeal {
                TagLabel(text: "직거래", color: .orange)
            } else if trade.isNewHigh {
                TagLabel(text: "신고가")
            }
            Text(Format.price(trade.price))
                .font(.subheadline.monospacedDigit().bold())
                .strikethrough(trade.cancelled)
                .foregroundStyle(trade.cancelled ? .secondary : .primary)
        }
    }
}
