#!/usr/bin/zsh

############################################################################
# zsh script which offers interactive selection menu 
# credit: https://codeberg.org/lukeflo/shell-scripts/src/branch/main/zshmenu.sh
#
# based on the answer by Guss on https://askubuntu.com/a/1386907/1771279
#
# call function with arguments:
# $1: Prompt text. newline characters are possible
# $2: Name of variable which contains the selected choice
# $3: Pass all selections to the function
#
# ex: 
# declare -a selections
# selections=(
# "Selection A"
# "Selection B"
# "Selection C"
# "Selection D"
# "Selection E"
# )
# choose_from_menu "Please make a choice:" selected_choice "${selections[@]}"
# echo "Selected choice: $selected_choice"

function choose_from_menu() {
    local prompt="$1" outvar="$2"
    shift
    shift
    # count had to be assigned the pure number of arguments
    local options=("$@") cur=1 count=$# index=0
    local esc=$(echo -en "\033") # cache ESC as test doesn't allow esc codes
    local instructions="Use ↑ ↓ / ← → / j k to select, ⏎ to submit, q to quit"
    echo -n "$prompt\n\n\033[38;5;8m$instructions\033[0m\n\n"
    # measure the rows of the menu, needed for erasing those rows when moving
    # the selection
    menu_rows=$#
    total_rows=$(($menu_rows + 1))
    up_keys="[D[Aj"
    down_keys="[C[Bk"
    while true
    do
        index=1 
        for o in "${options[@]}"
        do
            if [[ "$index" == "$cur" ]]
            then echo -e " \033[38;5;10m>\033[0m\033[38;5;2m$o\033[0m" # mark & highlight the current option
            else echo "  $o"
            fi
            index=$(( $index + 1 ))
        done
        printf "\n"
        # set mark for cursor
        printf "\033[s"
        # read in pressed key (differs from bash read syntax)
        read -s -r -k key
        if [[ $key == $esc ]]; then
            read -srk2 key # read 2 more chars
        fi
        if [[ $up_keys =~ "${key/"["/"\["}" ]] # move up
        then cur=$(( $cur - 1 ))
            [ "$cur" -lt 1 ] && cur=1 # make sure to not move out of selections scope
        elif [[ $down_keys =~ "${key/"["/"\["}" ]]  # move down
        then cur=$(( $cur + 1 ))
            [ "$cur" -gt $count ] && cur=$count # make sure to not move out of selections scope
        elif [[ "${key}" == $'\n' || $key == '' ]] # zsh inserts newline, \n, for enter - ENTER
        then break
        elif [[ $key == 'q' ]] 
        then exit 1
        fi
        # move back to saved cursor position
        printf "\033[u"
        # erase all lines of selections to build them again with new positioning
        for ((i = 0; i < $total_rows; i++)); do
            printf "\033[2k\r"
            printf "\033[F"
        done
    done
    # pass choosen selection to main body of script
    eval $outvar="'${options[$cur]}'"
}
