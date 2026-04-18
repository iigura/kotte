# kotte = Kanji Oriented Tiny Text Editor by Koji Iigura, 2025 - 2026.

import sys,os,subprocess,termios,signal,curses,unicodedata
from hashlib import sha256
from curses import A_REVERSE,A_NORMAL
from curses import KEY_LEFT,KEY_RIGHT,KEY_UP,KEY_DOWN,KEY_SLEFT,KEY_SRIGHT

ESC='\x1b'; CR='\n'; DEL='\x7f'
CtrlD,CtrlE,CtrlU,CtrlY=[chr(x) for x in (4,5,21,25)]
TabSize=4

StdScr=None; Done=False; SearchStr=None

isLastRow=lambda y: y==curses.LINES-3
charWidth=lambda x,c: TabSize-x%TabSize if c=='\t' \
          else 2 if unicodedata.east_asian_width(c) in 'WF' else 1
def logicalLineTop(buf,scanStartOffset):
    p=scanStartOffset
    while p>0 and buf[p-1]!='\n': p-=1
    return p
def getNextPos(buf,p,x,y=-1):
    c=buf[p]
    if c=='\n': return (0,y+1)
    w=charWidth(x,c)
    newX,newY=(x+w,y) if x+w<curses.COLS else (0,y+1)
    if p+1<len(buf):
        if newX+charWidth(newX,buf[p+1])>curses.COLS:
            newX=0; newY+=1
    return newX,newY
def lineTop(buf,start): # start=scanStartOffset
    if start<=0: return 0
    if buf[start-1]=='\n': return start
    x=0
    p=lineTopIndex=logicalLineTop(buf,min(start,len(buf)-1))
    while p<start:
        x,_=getNextPos(buf,p,x)
        if x==0: lineTopIndex=p+1
        p+=1
    return lineTopIndex
def prevLineTop(buf,start):
    return None if (p:=lineTop(buf,start))==0 else lineTop(buf,p-1)
def getCol(buf,targetIndex):
    p=logicalLineTop(buf,targetIndex)
    if p==targetIndex: return 0
    x=0
    while p<targetIndex:
        x,_=getNextPos(buf,p,x)
        p+=1
    return x
def nextLineTop(buf,start): # start=scanStartOffset
    if start>=len(buf)-1: return None
    if buf[start]=='\n': return start+1
    x=getCol(buf,start); p=start; dy=0
    while (x!=0 or dy==0) and p<len(buf):
        x,dy=getNextPos(buf,p,x,dy)
        p+=1
    return None if dy==0 else p
def lineEnd(buf,start):
    p=nextLineTop(buf,start)
    return len(buf) if p is None else max(0,p-1)
def isWordBoundary(c):
    return c in '\n\t' or unicodedata.category(c)[0] in 'ZPS'
def nextWordPos(buf,startIndex):
    if startIndex>=len(buf): return len(buf)
    p=startIndex
    if isWordBoundary(buf[p]):
        while p<len(buf) and isWordBoundary(buf[p]): p+=1
    else:
        while p<len(buf) and isWordBoundary(buf[p])==False: p+=1
        p=nextWordPos(buf,p) if p<len(buf) else len(buf)
    return p

def insert(state,pos,c,a=A_NORMAL):
    if pos is None:
        state.Buf.append(c); state.Attr.append(a)
    else:
        state.Buf.insert(pos,c); state.Attr.insert(pos,a)

class State:
    def __init__(self): self.reset()
    def reset(self,filePathForDisp='[NEW FILE]'):
        self.Buf=[]; self.Attr=[]
        self.AbsFilePath=None
        self.FilePathForDisp=filePathForDisp
        self.Index=self.PageStart=self.PageEnd=0
        self.Row=self.Col=self.TargetCol=0
        self.UpdateTargetCol=False
        self.SelectionBasePoint=-1
        self.LastIndexForDisplay=None 
        self.savedHash=None

    def getHash(self):
        return sha256(''.join(self.Buf).encode()).digest()
    def updateHash(self): self.savedHash=self.getHash()
    def isDirty(self): return self.savedHash!=self.getHash()

    def getFilePathStrForDisp(self):
        maxlen=curses.COLS//2
        home=os.path.expanduser('~')
        if self.AbsFilePath.startswith(home):
            candidate='~'+self.AbsFilePath[len(home):]
        else:
            candidate=self.AbsFilePath
        if len(candidate)<=maxlen: return candidate
        relpath=os.path.relpath(self.AbsFilePath,os.getcwd())
        if len(relpath)<=maxlen: return relpath
        if len(self.AbsFilePath)<=maxlen: return self.AbsFilePath
        return '...'+self.AbsFilePath[-(maxlen-3):]
    def updateTargetFile(self,targetFile):
        self.AbsFilePath=os.path.abspath(targetFile)
        self.FilePathForDisp=self.getFilePathStrForDisp()

    def top(self): self.Index=self.PageStart=0
    def updatePageStart(self):
        if self.Index<self.PageStart:
            self.PageStart=lineTop(self.Buf,self.Index)
        elif self.PageEnd<self.Index:
            self.PageStart=nextLineTop(self.Buf,self.PageStart)

    def moveToTargetCol(self,lineTopIndex):
        e=lineEnd(self.Buf,lineTopIndex)
        for p in range(lineTopIndex,e+1):
            x=getCol(self.Buf,p)
            if x>=self.TargetCol: break
        self.Index=p
        self.updatePageStart()

    def screenTop(self): self.Index=self.PageStart
    def screenBottom(self): self.Index=lineTop(self.Buf,self.PageEnd)
    def scrollDown(self):
        if self.PageStart==0: return
        self.PageStart=lineTop(self.Buf,self.PageStart-1)
    def ScrollUp(self):
        if self.PageEnd>=len(self.Buf): return
        p=nextLineTop(self.Buf,self.PageStart)
        if self.Index<p: self.Down()
        self.PageStart=p
    def ScrollDown(self):
        oldPS=self.PageStart
        self.scrollDown()
        if oldPS!=self.PageStart and self.Row>=curses.LINES-3:
            self.Up()
    def pageMove(self,scrollFunc,cursorAdjFunc):
        for _ in range(curses.LINES//2):
            scrollFunc()
            cursorAdjFunc()
    def PageUp(self):   self.pageMove(self.ScrollUp,   self.Down)
    def PageDown(self): self.pageMove(self.scrollDown, self.Up)

    def adjustPageStart(self):
        self.PageStart=self.Index
        for _ in range(self.Row): self.scrollDown()

    def Bottom(self):
        self.Index=lineTop(self.Buf,len(self.Buf))
        self.Row=curses.LINES-3
        self.adjustPageStart()

    def isSelected(self): return self.SelectionBasePoint>=0
    def getSelectedArea(self,index):
        start=min(index,self.SelectionBasePoint)
        end  =max(index,self.SelectionBasePoint)
        return start,end
    def updateAttr(self,index,op):
        start,end=self.getSelectedArea(index)
        for i in range(start,end):
            self.Attr[i]=op(self.Attr[i])
    def clrSelAttr(self,index): self.updateAttr(index,lambda a:a&~A_REVERSE)
    def setSelAttr(self,index): self.updateAttr(index,lambda a:a| A_REVERSE)
    def Select(self):
        if self.isSelected():
            self.clrSelAttr(self.Index)
            self.SelectionBasePoint=-1
        else:
            self.SelectionBasePoint=self.LastIndexForDisplay=self.Index

    def moveH(self,delta):
        p=max(0,min(len(self.Buf),self.Index+delta))
        if p!=self.Index:
            self.Index=p; self.updatePageStart(); self.UpdateTargetCol=True
    def Left(self): self.moveH(-1)
    def Right(self):self.moveH(+1)
    def Up(self):
        if(s:=prevLineTop(self.Buf,self.Index)) is None:
            self.Index=0
        else:
            self.moveToTargetCol(s)
    def Down(self):
        s=nextLineTop(self.Buf,self.Index)
        if s is None:
            self.Index=len(self.Buf)
            self.updatePageStart()
        else:
            self.moveToTargetCol(s)
    def LineBegin(self):
        self.Index=lineTop(self.Buf,self.Index)
        self.UpdateTargetCol=True
    def LineEnd(self): self.Index=lineEnd(self.Buf,self.Index)

    def nextWordIndex(self,index): return nextWordPos(self.Buf,index)
    def prevWordIndex(self,startIndex):
        p=lineTop(self.Buf,startIndex-1)
        while (q:=nextWordPos(self.Buf,p))<startIndex: p=q  
        return p
    def wordMove(self,func):
        self.Index=func(self.Index)
        self.UpdateTargetCol=True
    def WordForward(self):  self.wordMove(self.nextWordIndex)
    def WordBackward(self): self.wordMove(self.prevWordIndex)
    def deleteWord(self,startIndex=-1):
        if startIndex<0: startIndex=self.Index
        end=nextWordPos(self.Buf,startIndex)
        del self.Buf[startIndex:end-1]
        del self.Attr[startIndex:end-1]

    def FocusCenterRow(self):
        self.Row=(curses.LINES-3)//2
        self.adjustPageStart()

    def Del(self):
        if len(self.Buf)==0: return
        if self.isSelected():
            start,end=self.getSelectedArea(self.Index)
            del self.Buf[start:end+1]; del self.Attr[start:end+1]
            self.Select()
            self.Index=max(start-1,0); self.Right()
            self.adjustPageStart() 
        else:
            if self.Index<len(self.Buf):
                del self.Buf[self.Index]; del self.Attr[self.Index]
                self.Index=max(min(len(self.Buf),self.Index),0)
    def BackSpace(self):
        if self.Index>0: self.Left(); self.Del()
    def deleteLine(self):
        if self.isSelected():
            start,end=self.getSelectedArea(self.Index); end+=1
            self.Select()
        else:
            start=lineTop(self.Buf,self.Index)
            end=nextLineTop(self.Buf,self.Index)
        del self.Buf[start:end]; del self.Attr[start:end]
        self.Index=max(start-1,0); self.LineBegin(); self.Down()
        self.adjustPageStart()

    def Join(self):
        p=self.Index; self.LineEnd()
        while self.Buf[p]!=CR and p<len(self.Buf): p+=1
        if p<len(self.Buf) and self.Buf[p]==CR:
            self.Buf[p]=' '

S=State()

def notice(msg,waitMsg='(hit any key)'):
    y=curses.LINES-1
    StdScr.move(y,0); StdScr.clrtoeol()      
    StdScr.addstr(y,0,msg+(waitMsg if waitMsg is not None else ''))
    StdScr.refresh()
    if waitMsg: StdScr.get_wch()
def info(msg): notice(msg,waitMsg=None); return msg

def Display(statusLine=None):
    if S.isSelected():
        S.clrSelAttr(S.LastIndexForDisplay)
        S.setSelAttr(S.Index)
        S.LastIndexForDisplay=S.Index
    x=y=0; p=S.PageStart; StdScr.clear(); StdScr.move(0,0)
    while y<curses.LINES-2 and p<=len(S.Buf):
        c,a=(S.Buf[p],S.Attr[p]) if p<len(S.Buf) else (None,None)
        if p==S.Index: cursorX=x;cursorY=y
        if c=='\n': y+=1; x=0
        elif c is not None:
            w=charWidth(x,c)
            if x+w<=curses.COLS:
                StdScr.addstr(y,x,c,a)
            else:
                p-=1 # redo Buf[p]
            x+=w
        if x>=curses.COLS: y+=1; x=0
        p+=1
    S.PageEnd=p-1; filledRow = y>=curses.LINES-3
    S.Row,S.Col=cursorY,cursorX
    if S.UpdateTargetCol: S.TargetCol=S.Col

    if statusLine is None:
        statusLine=S.FilePathForDisp
        if S.isDirty(): statusLine+='(*)'
    posInfo=f" Row:{S.Row} Col:{S.Col} "
    totalWidth=curses.COLS
    numOfMiddleSpace=totalWidth-len(statusLine)-len(posInfo)
    s=statusLine+' '*numOfMiddleSpace+posInfo
    StdScr.addstr(curses.LINES-2,0,s,A_REVERSE)

    StdScr.move(S.Row,S.Col)
    StdScr.refresh()
    return filledRow

def Insert():
    info('--- INSERT ---')
    while True:
        filledRow=Display()
        StdScr.move(S.Row,S.Col); c=StdScr.get_wch()
        if c==ESC: break
        elif c in Act: Act[c]()
        elif isinstance(c,str):
            insert(S,S.Index,c); S.Index+=1
            if lineTop(S.Buf,S.Index)>S.PageEnd and filledRow:
                S.PageStart=nextLineTop(S.Buf,S.PageStart)
def Append():
    if 0<=S.Index<len(S.Buf) and S.Buf[S.Index]!='\n': S.Right()
    Insert()

def input(prompt='',initValue=''):
    y=curses.LINES-1
    buf=list(initValue); x=len(prompt+initValue); n=len(prompt)
    while True:
        s=prompt+''.join(buf); info(s)
        StdScr.move(y,x); c=StdScr.get_wch()
        if c==ESC: buf=None; break
        if c==CR : break
        if c==KEY_LEFT:
            if x>n: x-=1
        elif c==KEY_RIGHT:
            if x<len(s): x+=1
        elif c==DEL:
            if x>n: del buf[x-n-1]; x-=1
        elif x<curses.COLS-1 and isinstance(c,str): buf.insert(x-n,c); x+=1
    StdScr.move(y,0); StdScr.clrtoeol()
    return ''.join(buf) if buf is not None else None

def Quit(dummyParam=None):
    global Done
    if dummyParam: notice('invalid param (:q!)'); return
    Done=True    

def SafeQuit(dummyParam): 
    if dummyParam: notice('invalid param (:q)'); return
    if S.isDirty():
        ans=input('NOT saved. really Quit? (y/n):')
        if ans!='y': return
    Quit()

def Save(param=None):
    if param is None:
        if S.AbsFilePath is None: notice('no file name.'); return False
        outFilePath=S.AbsFilePath            
    else:
        p=param.strip().split()
        if len(p)!=1: notice('invalid param (:w)'); return False
        outFilePath=p[0]; S.updateTargetFile(outFilePath)
    with open(outFilePath,'w',encoding='utf-8') as f:
        f.write(''.join(Buf))
    info(f"SAVED:[{FilePathForDisp}]")
    S.updateHash()
    return True

def SaveAndQuit(dummyParam=None):
    if dummyParam: 
        notice('invalid param (:wq)')
    elif Save():
        Quit()

def Load(param):
    if len(S.Buf)>0 and S.isDirty():
        notice('current buffer is not saved.')
    elif param is None:
        S.reset()        
    else:
        p=param.strip().split()
        if len(p)!=1: notice('invalid param (:e)'); return
        filePath=p[0]
        if not os.path.exists(filePath):
            notice(f"no such file: '{filePath}'"); return
        S.reset(); S.updateTargetFile(filePath)
        with open(S.AbsFilePath) as f: S.Buf=list(f.read())
        S.Attr=[A_NORMAL for i in range(len(S.Buf))]
        S.Index=S.PageStart=0
    S.updateHash()

ColonCmd={':q':SafeQuit,':q!':Quit,':w':Save,':wq':SaveAndQuit,':e':Load}
def doColonCmd(cmdStr):
    tokens=cmdStr.strip().split(maxsplit=1)
    if len(tokens)==0: return    
    cmd=tokens[0]
    param=tokens[1] if len(tokens)>1 else None
    if cmd in ColonCmd:
        ColonCmd[cmd](param)
    else:
        notice(f"no such command [{cmd}].")
def Colon():
    if (s:=input('',':')): doColonCmd(s)

def search(targetRange):
    if SearchStr is None: return
    s=list(SearchStr)
    for i in targetRange:
        if S.Buf[i:i+len(s)]==s:
            S.Index=i
            if i<S.PageStart or S.PageEnd<i: S.adjustPageStart()
            return
    return info(f"pattern not found: {SearchStr}")
SearchNext=lambda: search(range(S.Index+1,len(S.Buf)-len(SearchStr)+1))
SearchPrev=lambda: search(range(S.Index-1,-1,-1))
def Search():
    global SearchStr
    if (s:=input('','/')):
        SearchStr=s[1:]
        return SearchNext()

def InsertLineBelow():
    p=nextLineTop(S.Buf,S.Index)
    if not (S.Col==0 and p is None):
        insert(S,p,'\n'); S.Index=len(S.Buf)-1 if p is None else p
        S.updatePageStart()
    S.Insert()
def InsertLineAbove():
    if lineTop(S.Buf,S.Index)==0:
        insert(S,0,'\n'); S.Index=0; Insert()
    else:
        S.Up(); S.InsertLineBelow()

def Replace():
    info('(replace to) '); c=StdScr.get_wch()
    if c==ESC: return
    if S.isSelected():
        start,end=S.getSelectedArea(S.Index) 
        S.Buf[start:end+1]=[c]*(end+1-start)
        S.Select()
    else:
        if 0<=S.Index<len(S.Buf): S.Buf[S.Index]=c

def getSecondKey(infoMsg):
    r,c=S.Row,S.Col; info(infoMsg); StdScr.move(r,c)
    return StdScr.get_wch()
def gen2strkFunc(firstKeyChar,mapTable):
    def func():
        c=getSecondKey(f"(Prefix {firstKeyChar})")
        if c in mapTable: mapTable[c]()
    return func
 
Act={KEY_LEFT: S.Left,     KEY_RIGHT:S.Right, KEY_UP:S.Up, KEY_DOWN:S.Down,
     KEY_SLEFT:S.LineBegin,KEY_SRIGHT:S.LineEnd, DEL:S.BackSpace,
     CtrlE:S.ScrollUp, CtrlY:S.ScrollDown, CtrlU:S.PageDown, CtrlD:S.PageUp,
}
Cmd={'h':S.Left,'l':S.Right,'k':S.Up,'j':S.Down,'v':S.Select,
     '0':S.LineBegin,'$':S.LineEnd,'g':S.top,'G':S.Bottom,
     'H':S.screenTop,'L':S.screenBottom,':':Colon,
     'w':S.WordForward,'b':S.WordBackward,'i':Insert,'a':Append,
     'o':InsertLineBelow,'O':InsertLineAbove,
     '/':Search,'n':SearchNext,'N':SearchPrev,
     'r':Replace,'x':S.Del,'J':S.Join,
     'd':gen2strkFunc('d',{'d':S.deleteLine,'w':S.deleteWord}),
     'z':gen2strkFunc('z',{'z':S.FocusCenterRow}),
     'Z':gen2strkFunc('Z',{'Z':SaveAndQuit}),
}

def disableFlowControl():
    result=subprocess.run(['stty','-g'],capture_output=True,text=True)
    originalSettings=result.stdout.strip()
    subprocess.run(['stty','-ixon','dsusp','undef'])
    return originalSettings
def restoreStty(backup): subprocess.run(['stty',backup])
def disableCtrlC():
    fd=sys.stdin.fileno()
    originalTermios=termios.tcgetattr(fd)
    newTermios=originalTermios[:]
    newTermios[3] &= ~(termios.ISIG|termios.ICANON|termios.ECHO)
    termios.tcsetattr(fd,termios.TCSADRAIN,newTermios)
    originalSigint=signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT,signal.SIG_IGN)
    return originalTermios,originalSigint
def restoreCtrlC(originalTermios,originalSigint):
    fd=sys.stdin.fileno()
    termios.tcsetattr(fd,termios.TCSADRAIN,originalTermios)
    signal.signal(signal.SIGINT,originalSigint)

def Main(stdscr,targetFilePath):
    global StdScr
    StdScr=stdscr
    Load(targetFilePath)
    curses.raw()
    s=None
    while not Done:
        Display(); S.UpdateTargetCol=False
        if s: info(s)
        c=stdscr.get_wch()
        s=Act[c]() if c in Act else Cmd[c]() if c in Cmd else None

def kotte(targetFilePath):
    originalTermios,originalSigint=disableCtrlC()
    originalSettings=disableFlowControl()
    os.environ.setdefault('ESCDELAY','1')
    try:
        curses.wrapper(Main,targetFilePath)
    finally:
        restoreStty(originalSettings)
        restoreCtrlC(originalTermios,originalSigint)

if __name__ == "__main__":
    targetFilePath=sys.argv[1] if len(sys.argv)==2 else None
    kotte(targetFilePath)
