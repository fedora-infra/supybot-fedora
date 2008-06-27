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
