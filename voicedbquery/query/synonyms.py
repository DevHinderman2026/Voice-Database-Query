"""Map spoken words to real table and column names."""

import difflib

# Built-in synonyms for the course sample databases. Users add their own per database.
DEFAULT_SYNONYMS = {
    "points": "pts", "point": "pts", "scoring": "pts",
    "rebounds": "reb", "rebound": "reb", "boards": "reb",
    "assists": "ast", "assist": "ast",
    "steals": "stl", "steal": "stl",
    "blocks": "blk", "block": "blk",
    "turnovers": "tov", "turnover": "tov",
    "games played": "gp", "games": "gp",
    "minutes": "min", "minutes played": "min",
    "field goal percentage": "fg_pct", "field goal": "fg_pct", "shooting percentage": "fg_pct",
    "three point percentage": "fg3_pct", "three pointers": "fg3m", "threes": "fg3m",
    "3 point percentage": "fg3_pct", "3 pointers": "fg3m", "3s": "fg3m", "3 point shots": "fg3m",
    "free throw percentage": "ft_pct", "free throws": "ftm",
    "plus minus": "plus_minus",
    "name": "full_name", "names": "full_name", "player name": "full_name", "team name": "full_name",
    "nicknames": "nickname", "cities": "city", "states": "state", "founded": "year_founded",
    "win loss": "wl", "result": "wl", "date": "game_date", "dates": "game_date",
    "year": "release_year", "years": "release_year", "release year": "release_year", "released": "release_year",
    "runtime": "runtime_minutes", "length": "runtime_minutes", "minutes long": "runtime_minutes",
    "rating": "avg_rating", "ratings": "avg_rating", "average rating": "avg_rating", "score": "avg_rating",
    "votes": "num_votes", "vote count": "num_votes",
    "born": "birth_year", "birth": "birth_year", "died": "death_year", "death": "death_year",
    "job": "profession", "jobs": "profession", "professions": "profession",
    "roles": "role", "characters": "character", "titles": "title",
    "film": "movies", "films": "movies", "movie": "movies",
    "person": "people", "actors": "people", "actor": "people", "directors": "people",
    "player": "players", "team": "teams",
    "player stats": "player_season_stats", "player season stats": "player_season_stats",
    "season stats": "player_season_stats", "player seasons": "player_season_stats",
    "team stats": "team_game_stats", "team game stats": "team_game_stats",
    "game stats": "team_game_stats", "game": "team_game_stats",
}


class SynonymMap:
    def __init__(self, user_synonyms: "dict | None" = None):
        self._map = {k.lower(): v for k, v in DEFAULT_SYNONYMS.items()}
        for k, v in (user_synonyms or {}).items():
            self._map[k.strip().lower()] = v

    def add(self, spoken: str, real: str) -> None:
        self._map[spoken.strip().lower()] = real

    def resolve(self, phrase: str, candidates) -> "str | None":
        """Return the real name from candidates that the phrase means, or None."""
        phrase = " ".join(phrase.lower().split())
        if not phrase:
            return None
        by_lower = {c.lower(): c for c in candidates}
        attempts = [phrase, phrase.replace(" ", "_"), phrase.replace(" ", "")]
        mapped = self._map.get(phrase)
        if mapped:
            attempts.insert(0, mapped.lower())
        for form in list(attempts):
            if form.endswith("ies"):
                attempts.append(form[:-3] + "y")
            if form.endswith("es"):
                attempts.append(form[:-2])
            if form.endswith("s"):
                attempts.append(form[:-1])
            else:
                attempts.append(form + "s")
        for form in attempts:
            if form in by_lower:
                return by_lower[form]
        close = difflib.get_close_matches(phrase.replace(" ", "_"), list(by_lower), n=1, cutoff=0.85)
        if close:
            return by_lower[close[0]]
        return None

    @staticmethod
    def suggest(phrase: str, candidates, n: int = 3) -> list:
        by_lower = {c.lower(): c for c in candidates}
        close = difflib.get_close_matches(phrase.lower().replace(" ", "_"), list(by_lower), n=n, cutoff=0.5)
        return [by_lower[c] for c in close]
