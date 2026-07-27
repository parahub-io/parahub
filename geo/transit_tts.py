"""Portuguese transit-stop name expansion for text-to-speech.

Carris Metropolitana ships a curated ``tts_stop_name`` (unabbreviated form) in
its GTFS ``stops.txt`` — a volunteer-maintained dataset that spells out street
abbreviations so a synthesizer says "Rua" not the letter "R". Other Portuguese
feeds (Carris Lisboa, Metro de Lisboa, CP, STCP, Transtejo) omit it, so
driver-mode TTS and screen readers get the abbreviated display name and read
"R" letter-by-letter.

This module reuses CM's abbreviation conventions to synthesize a TTS form at
serve time for pt feeds that lack one. It is a fallback only: callers use it
when ``Stop.tts_name`` is empty and the agency language is Portuguese, so any
upstream-provided tts_name always wins and the stored field keeps meaning
"exactly what the feed provided".

Deliberately conservative — a wrong expansion overrides the safe display-name
fallback, so only unambiguous abbreviations are expanded. Excluded on purpose
(CM does these, we don't): CM's phonetic respellings ("Estaçaão", "Práça") are
hand-tuned for CM's own voice engine, not the browser speechSynthesis a driver
actually uses; number-to-word ("1" -> "Um"); and the "(X)" crossing rewrite
("Cruzamento Entre..."). Ambiguous single letters (S=São/Santo/Sul, D=Dom/Dona/
Doutor) are left untouched rather than guessed.
"""
import re

# Multi-character abbreviations expanded regardless of case. Key is the token
# lowercased with any trailing "." stripped. These are unambiguous in a PT
# stop-name context.
_ALWAYS = {
    'av': 'Avenida', 'avª': 'Avenida', 'av.': 'Avenida',
    'estr': 'Estrada',
    'qta': 'Quinta', 'qtª': 'Quinta',
    'lgo': 'Largo', 'lg': 'Largo',
    'pç': 'Praça', 'pça': 'Praça', 'pca': 'Praça', 'praca': 'Praça',
    'rot': 'Rotunda',
    'urb': 'Urbanização',
    'esc': 'Escola',
    'trav': 'Travessa', 'tv': 'Travessa',
    'jd': 'Jardim',
    'merc': 'Mercado',
    'calç': 'Calçada', 'calc': 'Calçada', 'cç': 'Calçada',
    'bº': 'Bairro', 'brº': 'Bairro',
    'dr': 'Doutor',
    'drª': 'Doutora', 'dra': 'Doutora',
    'prof': 'Professor', 'profª': 'Professora',
    'eng': 'Engenheiro', 'engº': 'Engenheiro',
    'arq': 'Arquiteto',
    'gen': 'General',
    'cel': 'Coronel',
    'cmdt': 'Comandante',
    'pres': 'Presidente',
    'inf': 'Infante',
    'sra': 'Senhora', 'srª': 'Senhora',
    'sr': 'Senhor',
    'sta': 'Santa', 'stª': 'Santa',
    'sto': 'Santo',
}

# Abbreviations that collide with common lowercase Portuguese words, so they
# are only expanded when the original token was written in all caps (as a type
# prefix would be) — "EM"/"EN" the road classes vs "em" the preposition, "R"
# the street prefix vs a stray letter.
_UPPER_ONLY = {
    'R': 'Rua',
    'EM': 'Estrada Municipal',
    'EN': 'Estrada Nacional',
}

# Function words kept lowercase in Title Case (grammatical PT), except as the
# first word of the name. Lowercase "em" is the preposition; the road-class
# "EM" (Estrada Municipal) is caps and resolved earlier, so no collision.
_LOWER_WORDS = {'de', 'do', 'da', 'dos', 'das', 'e', 'à', 'ao', 'aos', 'às',
                'em', 'na', 'no', 'nas', 'nos'}


def _titlecase_word(w: str) -> str:
    # Capitalize the first alphabetic character, leave the rest as-is so accents
    # and inner capitals (e.g. ordinals "1º") survive.
    for i, ch in enumerate(w):
        if ch.isalpha():
            return w[:i] + ch.upper() + w[i + 1:]
    return w


def expand_pt_tts(name: str) -> str:
    """Expand a Portuguese stop display name into a TTS-friendly form.

    Pure and side-effect free. Returns '' for empty input. Only unambiguous
    abbreviations are expanded; everything else is passed through Title-cased.
    """
    if not name:
        return ''

    # Split into tokens on whitespace, keeping parentheses as their own tokens
    # so "(Quinta)" -> "( Quinta )" spacing matches and each word title-cases.
    raw = re.split(r'\s+', name.strip())
    out = []
    first_word_done = False
    for tok in raw:
        if not tok:
            continue
        # Peel leading/trailing parentheses into standalone tokens.
        lead = ''
        trail = ''
        while tok and tok[0] in '([':
            lead += tok[0]
            tok = tok[1:]
        while tok and tok[-1] in ')]':
            trail = tok[-1] + trail
            tok = tok[:-1]

        for ch in lead:
            out.append(ch)

        if tok:
            # Strip a trailing period before matching: feeds write the prefix
            # both ways ("R" and "R."), and the caps check must see the letters
            # not the dot ("R.".isupper() is still True, but "R." != key "R").
            clean = tok.rstrip('.')
            key = clean.lower()
            if clean.isupper() and clean in _UPPER_ONLY:
                out.append(_UPPER_ONLY[clean])
                first_word_done = True
            elif key in _ALWAYS:
                out.append(_ALWAYS[key])
                first_word_done = True
            else:
                if first_word_done and key in _LOWER_WORDS:
                    out.append(key)
                else:
                    out.append(_titlecase_word(tok))
                first_word_done = True

        for ch in trail:
            out.append(ch)

    return ' '.join(out)
