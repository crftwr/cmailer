import email
import poplib

#--------------------------------------------------------------------

class Account:

    def __init__( self, receiver, sender ):
        self.receiver = receiver
        self.sender = sender

    def receive( self ):
        return self.receiver.receive()

    def send( self ):
        return self.sender.send()
    
class Receiver:

    def __init__(self):
        pass

    def receive(self):
        pass

class Sender:

    def __init__(self):
        pass

    def send(self):
        pass

#--------------------------------------------------------------------

class Pop3Receiver( Receiver ):

    def __init__( self, server, port, username, password ):
        self.server = server
        self.port = port
        self.username = username
        self.password = password

    def receive(self):

        pop3 = poplib.POP3_SSL( server, port )
        pop3.user( username )
        pop3.pass_( password )
        
        num = len(pop3.list()[1])
        
        for i in xrange(num):
            message1 = pop3.retr(i+1)
            message2 = "\n".message1[1]
            message3 = email.parser.Parser().parsestr(message2)
            
            yield message3
        
        pop3.quit()

#--------------------------------------------------------------------

