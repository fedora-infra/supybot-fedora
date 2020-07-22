supybot-fedora is a Limnoria (supybot) plugin for general Fedora Community
actions. It implements the following commands:

* admins
* badges
* dctime
* fas
* fasinfo
* group
* hellomynameis
* himynameis
* karma
* localtime
* members
* mirroradmins
* nextmeeting
* nextmeetings
* pulls
* pushduty
* quote
* refresh
* showticket
* sponsors
* swedish
* vacation
* what
* whoowns
* wiki
* wikilink

# Development Environment

Vagrant allows contributors to get quickly up and running with a Noggin development
environment by automatically configuring a virtual machine. To get started, first
install the Vagrant and Virtualization packages needed, and start the libvirt
service:

```
$ sudo dnf install ansible libvirt vagrant-libvirt vagrant-sshfs vagrant-hostmanager
$ sudo systemctl enable libvirtd
$ sudo systemctl start libvirtd
```

Check out the code and run vagrant up:

```
$ git clone https://github.com/fedora-infra/supybot-fedora
$ cd supybot-fedora
$ vagrant up
```

To test out the bot, use an IRC client to connect to `irc.supybot.test` with the
nick `dudemcpants`, who has owner permissions over the bot. Finally, join the `#test`
channel, which supybot should also be in.

in the `#test` channel, prefix commands with `.`, e.g. `.nextmeetings`. But the prefix is
not needed when DMing supybot.

There are also the following commands to interact with the bot, and the bot logs:

```
$ fedora-supybot-start
$ fedora-supybot-stop
$ fedora-supybot-restart
$ fedora-supybot-logs
```
