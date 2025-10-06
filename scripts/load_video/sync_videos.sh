#!/usr/bin/env bash
set -euo pipefail

########################
# CONFIG PAR DÉFAUT    #
########################
REMOTE_USER="${REMOTE_USER:-root}"
REMOTE_HOST="${REMOTE_HOST:-153.92.222.24}"
REMOTE_DIR="${REMOTE_DIR:-/usr/local/lsws/Example/html/lumiere-academy/media/videos/}"  # trailing slash = contenu
LOCAL_DIR="${LOCAL_DIR:-./media/videos/}"    # trailing slash conseillé
SSH_KEY="${SSH_KEY:-}"                       # ex: /home/tonuser/.ssh/id_rsa  (laisser vide si mot de passe)

# Options rsync
RSYNC_OPTS=(-a -v -z
  --partial --partial-dir=.rsync-partial
  --human-readable
  --info=progress2,stats
  --out-format='%n'
)

# Options SSH (robustes et silencieuses)
SSH_OPTS=(-o ServerAliveInterval=60 -o ServerAliveCountMax=3 -o StrictHostKeyChecking=accept-new)

########################
# CHECKS & PREP        #
########################
command -v rsync >/dev/null 2>&1 || { echo "Erreur: rsync introuvable. Sous Ubuntu/WSL: sudo apt-get update && sudo apt-get install -y rsync"; exit 1; }
command -v ssh   >/dev/null 2>&1 || { echo "Erreur: ssh introuvable. Sous Ubuntu/WSL: sudo apt-get install -y openssh-client"; exit 1; }

mkdir -p "$LOCAL_DIR"

# Construit la commande SSH (avec clé si fournie)
if [[ -n "$SSH_KEY" ]]; then
  SSH_CMD=(ssh -i "$SSH_KEY" "${SSH_OPTS[@]}")
else
  SSH_CMD=(ssh "${SSH_OPTS[@]}")
fi

# Esthétique terminal (si dispo)
if command -v tput >/dev/null 2>&1 && [[ -t 1 ]]; then
  BOLD="$(tput bold)"; DIM="$(tput dim)"; RESET="$(tput sgr0)"
  CYAN="$(tput setaf 6)"; GREEN="$(tput setaf 2)"; YELLOW="$(tput setaf 3)"; MAGENTA="$(tput setaf 5)"
else
  BOLD=""; DIM=""; RESET=""; CYAN=""; GREEN=""; YELLOW=""; MAGENTA=""
fi

echo
echo "${BOLD}${CYAN}▶ Sync depuis ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}${RESET}"
echo "   → Vers ${BOLD}${LOCAL_DIR}${RESET}"
echo

START_EPOCH=$(date +%s)
CURRENT_FILE="(préparation...)"

########################
# RSYNC + BARRE        #
########################
# On pipe la sortie de rsync vers awk pour dessiner une barre de progression
# --info=progress2 donne une ligne cumulée avec % et ETA
{
  rsync "${RSYNC_OPTS[@]}" -e "${SSH_CMD[*]}" \
    "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}" \
    "${LOCAL_DIR}"
} 2>&1 | awk -v bold="$BOLD" -v dim="$DIM" -v reset="$RESET" -v green="$GREEN" -v yellow="$YELLOW" -v magenta="$MAGENTA" '
  function drawbar(pct, eta_text) {
    barwidth = 50
    filled = int((pct/100)*barwidth)
    empty  = barwidth - filled
    bar = ""
    for (i=0; i<filled; i++) bar = bar "#"
    for (i=0; i<empty;  i++) bar = bar "-"
    printf("\r\033[2K%s[%s]%s %3d%%%s  %s  %s\r",
           green, bar, reset, pct, reset, eta_text, "")
    fflush(stdout)
  }
  function printfile(name) {
    if (length(name) > 90) name = substr(name, 1, 87) "...";
    printf("\n%s📄 Fichier:%s %s\n", magenta, reset, name)
    fflush(stdout)
  }
  {
    line=$0
    # Ligne contenant la progression cumulée: ex "123,456,789  56%  12.34MB/s  0:01:23 (xfr#... to-chk=...)"
    if (line ~ /to-chk=/) {
      pct=0
      if (match(line, /([0-9]+)%/, m)) { pct = m[1]+0 }
      eta=""
      if (match(line, / ([0-9]+:[0-9]{2}:[0-9]{2}) /, t)) { eta = "ETA " t[1] }
      drawbar(pct, eta)
      next
    }
    # Suppression du bruit final de rsync, on affiche juste les stats plus tard
    if (line ~ /^(sent |total size|speedup is|bytes\/sec)/) { next }

    # Sinon, on considère que c est un nom de fichier (via --out-format=%n)
    if (length(line) > 0) {
      printfile(line)
    }
  }
  END {
    printf("\n")
  }
'

END_EPOCH=$(date +%s)
DUR=$(( END_EPOCH - START_EPOCH ))
printf "\n${BOLD}${GREEN}✔ Terminé${RESET} ${DIM}(durée: %02dh:%02dm:%02ds)${RESET}\n\n" \
  $((DUR/3600)) $(((DUR%3600)/60)) $((DUR%60))

echo "${DIM}Astuce: relance le script, rsync ne recopiera que les fichiers modifiés.${RESET}"
