This plugin is to interface with the Fedora Accounts System.

TO INSTALL:
1) Move the plugin to a directory where Supybot can access it.
2) @load Fedora
3) If you are not using the main FAS, run
     @config plugins.fedora.fas.url [rooturl]
4) In a PRIVMSG (/msg) to your bot, say
     config plugins.fedora.fas.username [username]
     config plugins.fedora.fas.password [password]
   (This information can only be accessed by bot owners.)
5) @reload Fedora

# Vagrant

First, create the vagrant setup with `vagrant up`

Once completed, you will be able to connect from your host to the IRC server
now running the the Vagrant guest VM, at "irc.supybot.test"

Next, ssh into the vagrant guest with `vagrant ssh`, and start the supybot 
with `supybot /home/vagrant/supybot-fedora/supybot-fedora.conf`

Then, in your IRC client, set your nick to "vagrant"
`/nick vagrant`

Then identify to supybot as vagrant, (the password is 'password')
`/msg supybot identify vagrant password`

First, load the plugin with:
`/msg supybot load Fedora`
Note that it will instantly fail due to the lack of FAS credentials

Next, set your FAS credentials in the plugin's config with:
`/msg supybot config plugins.fedora.fas.username [username]`
`/msg supybot config plugins.fedora.fas.password [password]`

Then load the plugin again with:
`/msg supybot load Fedora`


