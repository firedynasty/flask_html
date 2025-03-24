import os
import pandas as pd
import json
from flask import Flask, render_template, jsonify, request, send_from_directory

# Get the absolute path of the directory containing application.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, 
           template_folder=os.path.join(BASE_DIR, 'templates'),
           static_folder=os.path.join(BASE_DIR, 'static'))

# Load all matchups when the app starts
matchups_df = pd.read_csv(os.path.join(BASE_DIR, 'all_matchup_predictions.csv'))
team_list = sorted(list(set(matchups_df['team1'].tolist() + matchups_df['team2'].tolist())))

@app.route('/')
def index():
    try:
        return render_template('index.html', team_list=team_list)
    except Exception as e:
        return render_template('error.html', error=str(e))

@app.route('/api/teams')
def get_teams():
    try:
        return jsonify(team_list)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/predict', methods=['POST'])
def predict_matchup():
    try:
        # Get teams from request
        data = request.json
        team1 = data.get('team1')
        team2 = data.get('team2')
        
        if not team1 or not team2:
            return jsonify({"error": "Both teams must be provided"}), 400
        
        if team1 == team2:
            return jsonify({"error": "Please select two different teams"}), 400
        
        # Find the matchup in our pre-computed data
        matchup = None
        if len(matchups_df[(matchups_df['team1'] == team1) & (matchups_df['team2'] == team2)]) > 0:
            matchup = matchups_df[(matchups_df['team1'] == team1) & (matchups_df['team2'] == team2)].iloc[0].to_dict()
        elif len(matchups_df[(matchups_df['team1'] == team2) & (matchups_df['team2'] == team1)]) > 0:
            # Swap teams if found in reverse order
            matchup = matchups_df[(matchups_df['team1'] == team2) & (matchups_df['team2'] == team1)].iloc[0].to_dict()
            
            # We need to reverse the teams in the matchup
            temp = matchup.copy()
            # Swap team1 and team2 fields
            for field in ['wins', 'games', 'ortg', 'drtg', 'efg', 'tov_pct', 'orb_pct', 'ft_rate', 'advantages']:
                matchup[f'team1_{field}'] = temp[f'team2_{field}']
                matchup[f'team2_{field}'] = temp[f'team1_{field}']
            
            # Swap team names
            matchup['team1'], matchup['team2'] = temp['team2'], temp['team1']
            
            # Swap predictions
            matchup['team1_home_prediction'], matchup['team2_home_prediction'] = temp['team2_home_prediction'], temp['team1_home_prediction']
        
        if not matchup:
            return jsonify({"error": f"No prediction found for {team1} vs {team2}"}), 404
        
        # Format the results similar to the original application
        result_data = {
            "team1": team1,
            "team2": team2,
            "team1_stats": {
                "record": f"{matchup['team1_wins']}-{matchup['team1_games'] - matchup['team1_wins']}",
                "win_pct": matchup['team1_wins']/matchup['team1_games'] if matchup['team1_games'] > 0 else 0,
                "ortg": matchup['team1_ortg'],
                "drtg": matchup['team1_drtg'],
                "efg": matchup['team1_efg']
            },
            "team2_stats": {
                "record": f"{matchup['team2_wins']}-{matchup['team2_games'] - matchup['team2_wins']}",
                "win_pct": matchup['team2_wins']/matchup['team2_games'] if matchup['team2_games'] > 0 else 0,
                "ortg": matchup['team2_ortg'],
                "drtg": matchup['team2_drtg'],
                "efg": matchup['team2_efg']
            },
            "predictions": {
                "team1_home": "Win" if matchup['team1_home_prediction'] == 1 else "Loss",
                "team2_home": "Win" if matchup['team2_home_prediction'] == 1 else "Loss"
            },
            "advantages": {
                team1: matchup['team1_advantages'],
                team2: matchup['team2_advantages']
            }
        }
        
        # Add prediction summary
        if matchup['team1_home_prediction'] == 1 and matchup['team2_home_prediction'] == 0:
            result_data["prediction_summary"] = f"{team1} strongly favored - projected to win both at home and away"
            result_data["favorite"] = team1
        elif matchup['team1_home_prediction'] == 0 and matchup['team2_home_prediction'] == 1:
            result_data["prediction_summary"] = f"{team2} strongly favored - projected to win both at home and away"
            result_data["favorite"] = team2
        elif matchup['team1_home_prediction'] == 1 and matchup['team2_home_prediction'] == 1:
            result_data["prediction_summary"] = "Home court advantage is critical - home team projected to win in both scenarios"
            result_data["favorite"] = "home team"
        else:
            result_data["prediction_summary"] = "Unusual pattern detected - away team projected to win in both scenarios"
            result_data["favorite"] = "away team"
        
        # Determine overall favorite for neutral court
        if matchup['team1_home_prediction'] == matchup['team2_home_prediction']:
            favorite = team1 if matchup['team1_home_prediction'] == 1 else team2
            result_data["neutral_court"] = f"{favorite} favored to win regardless of venue"
        else:
            result_data["neutral_court"] = "Home court advantage appears to be the deciding factor"
        
        # Add key matchup factors
        result_data["matchup_factors"] = {
            "offensive": {
                team1: matchup['team1_ortg'],
                team2: matchup['team2_ortg'],
                "advantage": team1 if matchup['team1_ortg'] > matchup['team2_ortg'] else team2,
                "margin": abs(matchup['team1_ortg'] - matchup['team2_ortg'])
            },
            "defensive": {
                team1: matchup['team1_drtg'],
                team2: matchup['team2_drtg'],
                "advantage": team1 if matchup['team1_drtg'] < matchup['team2_drtg'] else team2,
                "margin": abs(matchup['team1_drtg'] - matchup['team2_drtg'])
            },
            "four_factors": {
                "shooting": {
                    team1: matchup['team1_efg'],
                    team2: matchup['team2_efg']
                },
                "turnovers": {
                    team1: matchup['team1_tov_pct'],
                    team2: matchup['team2_tov_pct']
                },
                "rebounding": {
                    team1: matchup['team1_orb_pct'],
                    team2: matchup['team2_orb_pct']
                },
                "free_throws": {
                    team1: matchup['team1_ft_rate'],
                    team2: matchup['team2_ft_rate']
                }
            }
        }
        
        return jsonify(result_data)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# Development server
if __name__ == '__main__':
    app.run(debug=True)
