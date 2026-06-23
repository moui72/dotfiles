########## Kubectl Aliases ##########
alias kc='kubectl'
alias kt='kubetail'
alias kcnet='kc get networkpolicies.networking.k8s.io -o yaml'
alias kcp='kc get pods'
alias kcd='kc get deployment'
alias kcds='kc get daemonset'
alias kcs='kc get statefulset'
alias kcda='kc get deployments --all-namespaces'
alias kcrrs='kc rollout restart statefulset'
alias kcrrd='kc rollout restart deployment'
alias kcpa='kc get pods --all-namespaces'
alias kcpn='kc get pods --all-namespaces | grep -v "Running\|Completed"'
alias kcpna='kc get pods --all-namespaces -o wide | grep -v Running'
alias kcn='kc get nodes'
alias kci='kc get ingress'
alias kcia='kc get ingress --all-namespaces'
alias kcnn='kc get nodes | grep NotReady'
alias kcpv='kc get pv'
alias kcpvc='kc get pvc'
# alias kcclean="kubectl get pods --all-namespaces | grep 'Error\|Completed' | awk {'print $1\" \"$2'} | xargs -n2 sh -c 'kubectl delete pod $2 -n $1 --grace-period=0 --force' sh"
alias troubleh="kubectl run jigar-test-shell --rm -i --tty --overrides='{\"spec\": {\"hostNetwork\": true}}' --image nicolaka/netshoot -- /bin/bash"
alias trouble="kubectl run jigar-test-shell --rm -i --tty --image nicolaka/netshoot -- /bin/bash"
alias kcv="kubectl view-utilization -h"
alias kcrollout="kubectl get deployments -o name | xargs kubectl rollout restart"
