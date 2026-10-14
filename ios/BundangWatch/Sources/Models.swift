import Foundation

/// 서버 JSON(snake_case)은 APIClient에서 camelCase로 변환해 디코딩한다.
/// 금액은 모두 만원 단위 정수.

enum Metric: String, CaseIterable, Identifiable, Codable {
    case composite
    case volume
    case growth
    case volumeChange = "volume_change"

    var id: String { rawValue }

    var title: String {
        switch self {
        case .composite: "종합"
        case .volume: "거래량"
        case .growth: "상승률"
        case .volumeChange: "거래증가"
        }
    }

    var explanation: String {
        switch self {
        case .composite: "거래량과 가격 상승률 순위를 반씩 반영한 점수"
        case .volume: "최근 3개월 실거래 건수 (해제·직거래 제외)"
        case .growth: "같은 면적끼리 최근 3개월 중위가격을 1년 전 같은 기간과 비교"
        case .volumeChange: "최근 3개월 거래 건수를 1년 전 같은 기간과 비교"
        }
    }
}

struct RankingItem: Codable, Identifiable, Hashable {
    let complexId: String
    let name: String
    let dong: String
    let buildYear: Int?
    let volume: Int
    let priorVolume: Int
    let volumeChange: Double?
    let growth: Double?
    let score: Double?
    let newHighs: Int
    let latestPrice: Int?
    let latestDealDate: Date?
    let latestArea: Double?

    var id: String { complexId }
}

struct RankingResponse: Codable {
    let asOf: Date
    let metric: Metric
    let windowDays: Int
    let lastCollectedAt: String?
    let items: [RankingItem]
}

struct ComplexInfo: Codable, Hashable {
    let id: String
    let name: String
    let dong: String
    let jibun: String?
    let buildYear: Int?
}

struct TradeItem: Codable, Identifiable, Hashable {
    let dealDate: Date
    let area: Double
    let areaBucket: Int
    let floor: Int?
    let price: Int
    let dealType: String?
    let cancelled: Bool
    let previousHigh: Int?

    // 서버 DB의 유니크 키와 같은 조합
    var id: String { "\(dealDate.timeIntervalSince1970)-\(area)-\(floor ?? -1)-\(price)" }
    var isNewHigh: Bool { previousHigh != nil }
    var isDirectDeal: Bool { dealType == "직거래" }
}

struct ComplexDetail: Codable {
    let complex: ComplexInfo
    let stats: RankingItem?
    let trades: [TradeItem]
}

struct NewHighItem: Codable, Identifiable, Hashable {
    let complexId: String
    let name: String
    let dong: String
    let dealDate: Date
    let area: Double
    let floor: Int?
    let price: Int
    let previousHigh: Int
    let increase: Double

    var id: String { "\(complexId)-\(dealDate.timeIntervalSince1970)-\(area)-\(floor ?? -1)-\(price)" }
}

struct Health: Codable {
    let status: String
    let trades: Int
    let lastCollectedAt: String?
}

/// 탭마다 NavigationStack이 따로 있으므로 단지 상세 이동은 이 값으로 통일한다.
struct ComplexRoute: Hashable {
    let id: String
    let name: String
}
