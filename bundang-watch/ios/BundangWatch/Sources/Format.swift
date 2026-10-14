import SwiftUI

enum Format {
    /// 157500(만원) -> "15억 7,500"
    static func price(_ manwon: Int) -> String {
        let eok = manwon / 10_000
        let rest = manwon % 10_000
        if eok == 0 { return "\(rest.formatted())만" }
        return rest == 0 ? "\(eok)억" : "\(eok)억 \(rest.formatted())"
    }

    static func price(_ manwon: Int?) -> String {
        manwon.map { price($0) } ?? "-"
    }

    /// 0.352 -> "+35.2%"
    static func percent(_ value: Double?) -> String {
        guard let value else { return "-" }
        return value.formatted(.percent.precision(.fractionLength(1)).sign(strategy: .always()))
    }

    /// 84.97 -> "85㎡(26평)"  ※ 평은 전용면적 기준
    static func area(_ squareMeters: Double) -> String {
        "\(Int(squareMeters.rounded()))㎡(\(Int((squareMeters / 3.3058).rounded()))평)"
    }

    static func date(_ date: Date) -> String {
        date.formatted(.dateTime.year(.twoDigits).month(.twoDigits).day(.twoDigits))
    }

    /// 국내 시세 표기 관례: 상승 빨강, 하락 파랑
    static func changeColor(_ value: Double?) -> Color {
        guard let value else { return .secondary }
        if value > 0 { return .red }
        if value < 0 { return .blue }
        return .secondary
    }
}

struct TagLabel: View {
    let text: String
    var color: Color = .red

    var body: some View {
        Text(text)
            .font(.caption2.bold())
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(color.opacity(0.15), in: Capsule())
            .foregroundStyle(color)
    }
}
