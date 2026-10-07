import flet as ft
import numpy as np
from scipy.optimize import minimize
from scipy.stats import poisson
import csv
from datetime import datetime
import os

max_goals = 6  

def main(page: ft.Page):
    page.title = "VFooty Predictor Engine"
    page.scroll = "adaptive"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 15

    # 1. UI INPUT FIELDS
    bankroll_input = ft.TextField(label="Wallet Balance", value="50000", keyboard_type=ft.KeyboardType.NUMBER)
    home_input = ft.TextField(label="Home Odds", value="1.55", keyboard_type=ft.KeyboardType.NUMBER)
    draw_input = ft.TextField(label="Draw Odds", value="4.50", keyboard_type=ft.KeyboardType.NUMBER)
    away_input = ft.TextField(label="Away Odds", value="6.20", keyboard_type=ft.KeyboardType.NUMBER)
    
    time_dropdown = ft.Dropdown(
        label="Match Elapsed Status",
        options=[
            ft.dropdown.Option("0", "Pre-Match (3 mins remaining)"),
            ft.dropdown.Option("1", "1 Minute Played (2 mins remaining)"),
            ft.dropdown.Option("2", "Half-Time (1 min remaining)"),
        ],
        value="0"
    )

    # UI OUTPUT LABELS
    lambda_text = ft.Text(value="", size=14, color=ft.colors.BLUE_200)
    scores_text = ft.Text(value="", size=15, weight=ft.FontWeight.BOLD, color=ft.colors.AMBER_300)
    markets_text = ft.Text(value="", size=14, color=ft.colors.WHITE70)
    rec_text = ft.Text(value="Enter odds parameters above and click run.", size=15, weight=ft.FontWeight.BOLD, color=ft.colors.LIGHT_GREEN_ACCENT_400)

    # 2. PROCESSING ALGORITHM
    def calculate_predictions(e):
        try:
            bankroll = float(bankroll_input.value)
            home_odds = float(home_input.value)
            draw_odds = float(draw_input.value)
            away_odds = float(away_input.value)
            time_elapsed = int(time_dropdown.value)
        except ValueError:
            rec_text.value = "⚠️ ERROR: Please enter valid numbers only!"
            page.update()
            return

        time_decay = (3.0 - float(time_elapsed)) / 3.0

        # MODULE 1: Strip Juice
        raw_p_home = 1.0 / home_odds
        raw_p_draw = 1.0 / draw_odds
        raw_p_away = 1.0 / away_odds
        total_market_sum = raw_p_home + raw_p_draw + raw_p_away

        p_home = raw_p_home / total_market_sum
        p_draw = raw_p_draw / total_market_sum
        p_away = raw_p_away / total_market_sum

        def loss_function(x):
            lambda_home, lambda_away = x, x
            if lambda_home <= 0 or lambda_away <= 0:
                return 1e6
            p_matrix = np.outer(
                poisson.pmf(np.arange(max_goals + 1), lambda_home),
                poisson.pmf(np.arange(max_goals + 1), lambda_away)
            )
            sim_draw = np.sum(np.diag(p_matrix))
            sim_home = np.sum(np.tril(p_matrix, -1))
            sim_away = np.sum(np.triu(p_matrix, 1))
            return (sim_home - p_home)**2 + (sim_draw - p_draw)**2 + (sim_away - p_away)**2

        initial_guess = [1.2, 1.2]
        result = minimize(loss_function, initial_guess, method='Nelder-Mead')
        
        lambda_home = result.x * time_decay
        lambda_away = result.x * time_decay

        lambda_text.value = f"Expected Goals -> Home (λ): {lambda_home:.3f} | Away (λ): {lambda_away:.3f}"

        # MODULE 2: Matrix Grid
        home_probs = poisson.pmf(np.arange(max_goals + 1), lambda_home)
        away_probs = poisson.pmf(np.arange(max_goals + 1), lambda_away)
        score_matrix = np.outer(home_probs, away_probs)

        score_list = []
        for h in range(max_goals + 1):
            for a in range(max_goals + 1):
                prob = score_matrix[h, a]
                score_list.append((f"{h}-{a}", prob))
                
        score_list.sort(key=lambda item: item, reverse=True)
        top_scores_str = []
        
        scores_display = "🏆 TOP 2 EXPECTED SCORES:\n"
        for score_str, prob in score_list[:2]:
            scores_display += f" • {score_str} ({prob * 100:.1f}%)\n"
            top_scores_str.append(f"{score_str}({prob*100:.1f}%)")
        scores_text.value = scores_display

        over_25_prob = 0.0
        gg_prob = 0.0
        for h in range(max_goals + 1):
            for a in range(max_goals + 1):
                prob = score_matrix[h, a]
                if (h + a) >= 3:
                    over_25_prob += prob
                if h > 0 and a > 0:
                    gg_prob += prob

        under_25_prob = 1.0 - over_25_prob
        no_gg_prob = 1.0 - gg_prob

        markets_text.value = (
            f"Over 2.5 Goals: {over_25_prob * 100:.1f}%  (Under: {under_25_prob * 100:.1f}%)\n"
            f"Goal-Goal (GG): {gg_prob * 100:.1f}%  (No GG: {no_gg_prob * 100:.1f}%)"
        )

        # MODULE 3: Kelly Staking
        recommendations = []
        rec_display = "🔥 SUGGESTED ACTIONS:\n"
        
        def calculate_kelly_stake(prob, odds):
            edge = (prob * odds) - 1
            if edge > 0:
                fraction = edge / (odds - 1)
                return edge, min(fraction * 0.25, 0.10)
            return edge, 0.0

        over_edge, over_stake_pct = calculate_kelly_stake(over_25_prob, 1.90)
        if over_edge > 0.02:
            rec_display += f"✔ PLAY OVER 2.5 GOALS (Stake: {bankroll * over_stake_pct:.0f} UGX)\n"
            recommendations.append("OVER 2.5")
            
        gg_edge, gg_stake_pct = calculate_kelly_stake(gg_prob, 1.85)
        if gg_edge > 0.02:
            rec_display += f"✔ PLAY GOAL-GOAL (GG) (Stake: {bankroll * gg_stake_pct:.0f} UGX)\n"
            recommendations.append("GG")

        if not recommendations:
            rec_text.value = "⚠️ SIGNAL: SKIP\nNo high-confidence edge found."
            rec_text.color = ft.colors.ORANGE_300
            rec_summary = "SKIP"
        else:
            rec_text.value = rec_display
            rec_text.color = ft.colors.LIGHT_GREEN_ACCENT_400
            rec_summary = ", ".join(recommendations)

        # MODULE 4: CSV Log
        csv_filename = "vfooty_predictions.csv"
        file_exists = os.path.isfile(csv_filename)
        log_data = {
            "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Home_Odds": home_odds, "Draw_Odds": draw_odds, "Away_Odds": away_odds,
            "Over_25": f"{over_25_prob*100:.1f}%", "GG": f"{gg_prob*100:.1f}%",
            "Recommendation": rec_summary
        }
        with open(csv_filename, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=log_data.keys())
            if not file_exists:
                writer.writeheader()
            writer.writerow(log_data)
        page.update()

    calc_button = ft.ElevatedButton(
        text="Calculate Predictions",
        height=45,
        on_click=calculate_predictions
    )

    # 3. UNWRAPPED FLAT VIEW LAYOUT
    layout_view = ft.Column(
        controls=[
            ft.Text("VFOOTY PREDICTOR v2.0", size=18, weight=ft.FontWeight.BOLD),
            bankroll_input,
            home_input,
            draw_input,
            away_input,
            time_dropdown,
            calc_button,
            ft.Divider(),
            lambda_text,
            scores_text,
            markets_text,
            ft.Divider(),
            rec_text
        ],
        spacing=12
    )
    
    page.add(layout_view)

if __name__ == "__main__":
    ft.app(target=main, view=ft.AppView.FLET_APP)
