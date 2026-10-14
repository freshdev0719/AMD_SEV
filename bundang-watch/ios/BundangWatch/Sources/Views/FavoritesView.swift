import SwiftUI

struct FavoritesView: View {
    @Environment(FavoritesStore.self) private var favorites

    var body: some View {
        NavigationStack {
            List {
                ForEach(favorites.items) { complex in
                    NavigationLink(complex.name, value: ComplexRoute(id: complex.id, name: complex.name))
                }
                .onDelete { favorites.remove(atOffsets: $0) }
            }
            .overlay {
                if favorites.items.isEmpty {
                    ContentUnavailableView(
                        "관심 단지가 없습니다",
                        systemImage: "star",
                        description: Text("단지 상세 화면에서 ☆를 눌러 추가하세요.")
                    )
                }
            }
            .navigationTitle("관심단지")
            .navigationDestination(for: ComplexRoute.self) { ComplexDetailView(route: $0) }
        }
    }
}
