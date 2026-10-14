import SwiftUI

struct SettingsView: View {
    @AppStorage(SettingsKey.serverURL) private var serverURL = APIClient.defaultURL
    @State private var draftURL = ""
    @State private var status: String?
    @State private var isChecking = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("http://localhost:8000", text: $draftURL)
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .onSubmit(save)
                    Button(isChecking ? "확인 중…" : "저장 후 연결 확인", action: save)
                        .disabled(isChecking)
                    if let status {
                        Text(status).font(.footnote).foregroundStyle(.secondary)
                    }
                } header: {
                    Text("서버 주소")
                } footer: {
                    Text("실제 아이폰에서는 localhost 대신 Mac의 IP 주소(예: http://192.168.0.10:8000)나 배포한 HTTPS 주소를 입력하세요.")
                }

                Section("지표 설명") {
                    ForEach(Metric.allCases) { metric in
                        LabeledContent(metric.title) {
                            Text(metric.explanation).multilineTextAlignment(.trailing)
                        }
                        .font(.footnote)
                    }
                }

                Section("데이터") {
                    Text("국토교통부 아파트 매매 실거래가 공개 자료를 바탕으로 합니다. 실거래는 계약 후 30일 안에 신고되므로 최근 거래 수는 시간이 지나며 늘어날 수 있습니다. 투자 판단의 참고 자료로만 사용하세요.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("설정")
            .onAppear { draftURL = serverURL }
        }
    }

    private func save() {
        serverURL = draftURL.trimmingCharacters(in: .whitespacesAndNewlines)
        isChecking = true
        status = nil
        Task {
            defer { isChecking = false }
            do {
                let health = try await APIClient(serverURL).health()
                status = "연결됨 · 거래 \(health.trades.formatted())건 · 마지막 수집 \(health.lastCollectedAt ?? "-")"
            } catch {
                status = "연결 실패: \(error.localizedDescription)"
            }
        }
    }
}
