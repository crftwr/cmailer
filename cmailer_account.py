import email.parser
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

class Email:

    def __init__( self, text ):

        self.msg = email.parser.Parser().parsestr(text)

        # Subject
        subject, encoding = email.Header.decode_header(self.msg.get("Subject"))[0]
        if encoding:
            subject = unicode(subject, encoding)
        self.subject = subject
        
        # DateTime
        date = self.msg.get('Date')
        date = email.utils.parsedate(date)
        self.date = date

#--------------------------------------------------------------------

class Pop3Receiver( Receiver ):

    def __init__( self, server, port, username, password ):
        self.server = server
        self.port = port
        self.username = username
        self.password = password

    def receive(self):

        pop3 = poplib.POP3_SSL( self.server, self.port )
        pop3.user( self.username )
        pop3.pass_( self.password )
        
        num = len(pop3.list()[1])
        
        for i in xrange(num):
            message = pop3.retr(i+1)
            text = "\n".join(message[1])

            yield Email(text)
        
        pop3.quit()

#--------------------------------------------------------------------

