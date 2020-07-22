# .bashrc

alias fedora-supybot-start="sudo systemctl start supybot.service; sudo systemctl status supybot.service"
alias fedora-supybot-logs="sudo journalctl -u supybot.service"
alias fedora-supybot-restart="sudo systemctl restart supybot.service; sudo systemctl status supybot.service"
alias fedora-supybot-stop="sudo systemctl stop supybot.service; sudo systemctl status supybot.service"

cd /vagrant
