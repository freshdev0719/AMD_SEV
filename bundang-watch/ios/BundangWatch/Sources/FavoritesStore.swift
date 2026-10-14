import Foundation
import Observation

struct FavoriteComplex: Codable, Hashable, Identifiable {
    let id: String
    let name: String
}

/// 관심 단지 목록. 기기 안(UserDefaults)에만 저장한다.
@Observable
final class FavoritesStore {
    private static let storageKey = "favorites"

    private(set) var items: [FavoriteComplex] = []

    init() {
        if let data = UserDefaults.standard.data(forKey: Self.storageKey),
           let saved = try? JSONDecoder().decode([FavoriteComplex].self, from: data) {
            items = saved
        }
    }

    func contains(_ id: String) -> Bool {
        items.contains { $0.id == id }
    }

    func toggle(_ complex: FavoriteComplex) {
        if contains(complex.id) {
            items.removeAll { $0.id == complex.id }
        } else {
            items.append(complex)
        }
        save()
    }

    func remove(atOffsets offsets: IndexSet) {
        items.remove(atOffsets: offsets)
        save()
    }

    private func save() {
        if let data = try? JSONEncoder().encode(items) {
            UserDefaults.standard.set(data, forKey: Self.storageKey)
        }
    }
}
