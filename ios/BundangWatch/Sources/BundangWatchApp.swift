import SwiftUI

@main
struct BundangWatchApp: App {
    @State private var favorites = FavoritesStore()

    var body: some Scene {
        WindowGroup {
            TabView {
                RankingView()
                    .tabItem { Label("랭킹", systemImage: "chart.bar.fill") }
                NewHighsView()
                    .tabItem { Label("신고가", systemImage: "arrow.up.right.circle.fill") }
                FavoritesView()
                    .tabItem { Label("관심단지", systemImage: "star.fill") }
                SettingsView()
                    .tabItem { Label("설정", systemImage: "gearshape.fill") }
            }
            .environment(favorites)
        }
    }
}
