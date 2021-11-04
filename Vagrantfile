# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant.configure(2) do |config|
    config.vm.box_url = "https://download.fedoraproject.org/pub/fedora/linux/releases/34/Cloud/x86_64/images/Fedora-Cloud-Base-Vagrant-34-1.2.x86_64.vagrant-libvirt.box"
    config.vm.box = "f34-cloud-libvirt"
    config.vm.hostname = "irc.supybot.test"
    config.vm.synced_folder ".", "/vagrant", type: "sshfs"
    config.hostmanager.enabled = true
    config.hostmanager.manage_host = true
    config.vm.provider :libvirt do |libvirt|
      libvirt.cpus = 2
      libvirt.memory = 2048
    end

    config.vm.provision "ansible" do |ansible|
      ansible.playbook = "devel/ansible/playbook.yml"
    end
end
