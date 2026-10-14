import Foundation

enum SettingsKey {
    static let serverURL = "serverURL"
}

enum APIError: LocalizedError {
    case invalidURL
    case badResponse
    case http(Int)

    var errorDescription: String? {
        switch self {
        case .invalidURL: "서버 주소가 올바르지 않습니다. 설정 탭에서 확인하세요."
        case .badResponse: "서버 응답을 해석할 수 없습니다."
        case .http(let code): "서버 오류 (HTTP \(code))"
        }
    }
}

struct APIClient {
    /// 시뮬레이터에서는 Mac의 localhost에 바로 붙는다.
    /// 실제 아이폰에서는 Mac의 IP(예: http://192.168.0.10:8000)나 배포한 HTTPS 주소를 넣는다.
    static let defaultURL = "http://localhost:8000"

    let baseURL: URL

    init(_ urlString: String) throws {
        let trimmed = urlString.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let url = URL(string: trimmed), url.scheme != nil, url.host() != nil else {
            throw APIError.invalidURL
        }
        baseURL = url
    }

    func rankings(metric: Metric, limit: Int = 10) async throws -> RankingResponse {
        try await get("rankings", query: [
            URLQueryItem(name: "metric", value: metric.rawValue),
            URLQueryItem(name: "limit", value: String(limit)),
        ])
    }

    func complex(id: String) async throws -> ComplexDetail {
        try await get("complexes/\(id)")
    }

    func newHighs(days: Int) async throws -> [NewHighItem] {
        try await get("new-highs", query: [URLQueryItem(name: "days", value: String(days))])
    }

    func health() async throws -> Health {
        try await get("health")
    }

    private static let decoder: JSONDecoder = {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "Asia/Seoul")
        formatter.dateFormat = "yyyy-MM-dd"

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .formatted(formatter)
        return decoder
    }()

    private func get<T: Decodable>(_ path: String, query: [URLQueryItem] = []) async throws -> T {
        guard var components = URLComponents(url: baseURL.appending(path: path), resolvingAgainstBaseURL: false) else {
            throw APIError.invalidURL
        }
        if !query.isEmpty {
            components.queryItems = query
        }
        guard let url = components.url else { throw APIError.invalidURL }

        let (data, response) = try await URLSession.shared.data(from: url)
        guard let http = response as? HTTPURLResponse else { throw APIError.badResponse }
        guard (200..<300).contains(http.statusCode) else { throw APIError.http(http.statusCode) }
        do {
            return try Self.decoder.decode(T.self, from: data)
        } catch {
            throw APIError.badResponse
        }
    }
}

extension Error {
    /// 화면 전환·새로고침으로 취소된 요청은 오류로 보여주지 않는다.
    var isCancellation: Bool {
        if self is CancellationError { return true }
        if let urlError = self as? URLError, urlError.code == .cancelled { return true }
        return false
    }
}
