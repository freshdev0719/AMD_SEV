import SwiftUI

struct NewHighsView: View {
    @AppStorage(SettingsKey.serverURL) private var serverURL = APIClient.defaultURL
    @State private var days = 30
    @State private var items: [NewHighItem]?
    @State private var errorMessage: String?

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Picker("기간", selection: $days) {
                        Text("7일").tag(7)
                        Text("30일").tag(30)
                        Text("90일").tag(90)
                    }
                    .pickerStyle(.segmented)
                } footer: {
                    Text("같은 단지·같은 면적에서 이전 모든 거래보다 높은 가격 (해제·직거래 제외)")
                }

                if let items {
                    ForEach(items) { item in
                        NavigationLink(value: ComplexRoute(id: item.complexId, name: item.name)) {
                            NewHighRow(item: item)
                        }
                    }
                }
            }
            .overlay {
                if let errorMessage, items == nil {
                    ContentUnavailableView("불러오지 못했습니다", systemImage: "wifi.exclamationmark", description: Text(errorMessage))
                } else if items == nil {
                    ProgressView()
                } else if items?.isEmpty == true {
                    ContentUnavailableView("기간 내 신고가가 없습니다", systemImage: "chart.line.flattrend.xyaxis")
                }
            }
            .navigationTitle("신고가")
            .navigationDestination(for: ComplexRoute.self) { ComplexDetailView(route: $0) }
            .task(id: "\(days)|\(serverURL)") { await load() }
            .refreshable { await load() }
        }
    }

    private func load() async {
        do {
            items = try await APIClient(serverURL).newHighs(days: days)
            errorMessage = nil
        } catch let error where error.isCancellation {
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

private struct NewHighRow: View {
    let item: NewHighItem

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text(item.name).font(.headline).lineLimit(1)
                Text("\(item.dong) · \(Format.area(item.area)) · \(Format.date(item.dealDate))")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 4) {
                Text(Format.price(item.price)).font(.headline.monospacedDigit())
                Text("\(Format.percent(item.increase)) (직전 \(Format.price(item.previousHigh)))")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.red)
            }
        }
    }
}
