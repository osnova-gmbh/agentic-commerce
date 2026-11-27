"""The buyer's persistent finance and Affinidi identity."""

from cogit_messaging_shim.affinidi.runtime import AgentIdentity, AgentIdentityRuntime

identity = AgentIdentity("buyer-agent", "buyer", ".state/keys/buyer-agent.key")


def identity_commands():
    return identity.cli_commands()


def create_runtime():
    return AgentIdentityRuntime(identity)


def boris_client(**kwargs):
    return identity.boris_client(**kwargs)
