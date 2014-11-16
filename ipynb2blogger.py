#!/usr/bin/env python

import argparse
import httplib2
import json
import logging
import os
# Google APIs
from apiclient.discovery import build
from oauth2client import client
from oauth2client.file import Storage
from oauth2client.tools import run_flow
from oauth2client.tools import argparser
from googleapiclient.errors import HttpError


def main():
  """
  Parse the command line positional and optional arguments.
  This is the highest level procedure that invokes the real workers.
  """
  global debug

  parser = argparse.ArgumentParser(
    description='ipynb2blogger.py is a tool for posting iPython notebooks to blogger.',
    parents=[argparser],
    epilog='Written by A.Adcroft, 2014 (https://github.com/Adcroft).')
  parser.add_argument('-d', '--debug', action='store_true', help='Turn on debugging.')
  subparsers = parser.add_subparsers()#help='sub-command help')

  parser_whoAmI = subparsers.add_parser('whoami', help='Display username you are authenticated as.')
  parser_whoAmI.set_defaults(action=whoAmI)

  parser_listBlogs = subparsers.add_parser('listblogs', help='Lists blogs the authenticated user can post to.')
  parser_listBlogs.set_defaults(action=listBlogs)

  parser_listPosts = subparsers.add_parser('list', help='Lists published posts in blog at url.')
  parser_listPosts.add_argument('url', type=str, help='URL of blogger blog.')
  parser_listPosts.set_defaults(action=listPosts)
  group = parser_listPosts.add_mutually_exclusive_group()
  group.add_argument('-d', '--draft', action='store_true', help='List draft posts.')
  group.add_argument('-s', '--scheduled', action='store_true', help='List scheduled posts.')

  parser_insertPost = subparsers.add_parser('insert', help='Upload a post.')
  parser_insertPost.add_argument('url', type=str, help='URL of blogger blog.')
  parser_insertPost.add_argument('file', type=str, help='File to upload as the post.')
  parser_insertPost.set_defaults(action=insertPost)

  cArgs = parser.parse_args()
  #if cArgs.debug:
  #  httplib2.debuglevel = 4

  cArgs.action(cArgs, debug=cArgs.debug)


def whoAmI(args, debug=False):
  """
  Displays name of authenticated user.
  """

  service, http = authenticate(args)

  users = service.users()
  if debug: print 'users =',users
  
  # Retrieve this user's profile information
  request = users.get(userId='self')
  if debug: print 'users().get(userId="self") =',request.to_json()
  response = request.execute(http=http)
  if debug: print 'response =',json.dumps(response,indent=2)
  print 'This user\'s display name is: %s' % response['displayName']


def listBlogs(args, debug=False):
  """
  Lists blogs associated with authenticated user.
  """

  service, http = authenticate(args)

  # Retrieve the list of Blogs this user has write privileges on
  blogs = service.blogs()
  if debug: print 'blogs =',blogs
  request = blogs.listByUser(userId='self')
  if debug: print 'blogs().listByUser(userId="self") =',request.to_json()
  response = request.execute()
  if debug: print 'response =',json.dumps(response,indent=2)
  if 'items' in response:
    for blog in response['items']:
      if debug: print 'blog =',json.dumps(blog,indent=2)
      print 'The blog named \'%s\' is at: %s' % (blog['name'], blog['url'])
  else: print 'No blogs found'


def listPosts(args, debug=False):
  """
  Lists posts at blog.
  """
  service, http = authenticate(args)

  # Retrieve the list of Blogs this user has write privileges on
  blogs = service.blogs()
  if debug: print 'blogs =',blogs

  # Find blog by URL
  request = blogs.getByUrl(url=args.url)
  if debug: print 'blogs.getByUrl(url=args.url) =',request.to_json()
  response = request.execute()
  if debug: print 'response =',json.dumps(response, indent=2)
  #response = blogs.getByUrl(url=args.url).execute()
  blogId = response['id']
  if debug: print 'blogId =',blogId

  # Options
  status = None
  if args.draft: status = 'draft'
  if args.scheduled: status = 'scheduled'

  # Get list of posts
  posts = service.posts()
  if debug: print 'posts =',posts
  request = posts.list(blogId=blogId, status=status)
  if debug: print 'posts().list(blogId=blogId) =',request.to_json()
  response = request.execute()
  #response = service.posts().list(blogId=blogId).execute()
  if debug: print 'response =',json.dumps(response, indent=2)
  while 'items' in response:
    for item in response['items']:
      print item['published'],item['title']
      if debug: print json.dumps(item, indent=2)
    if 'nextPageToken' in response:
      request = posts.list(blogId=blogId, pageToken=response['nextPageToken'], status=status)
      response = request.execute()
    else:
      response = {} # Leave while loop


def insertPost(args, debug=False):
  """
  Inserts a file as a post to a blog.
  """

  # Build body of post
  body = {}
  body['kind'] = 'blogger#post'

  title = os.path.splitext( os.path.basename(args.file) )[0]
  body['title'] = title

  # Read mathJax header
  mathJaxFile = os.path.join(os.path.dirname(__file__),'mathJax.html')
  with open (mathJaxFile, 'r') as htmlfile:
    mathJax = htmlfile.read()

  # Read file to post
  with open (args.file, 'r') as htmlfile:
    html = htmlfile.read()
  body['content'] = mathJax + html

  # Start communications with blogger
  service, http = authenticate(args)

  # Retrieve the list of Blogs this user has write privileges on
  blogs = service.blogs()
  if debug: print 'blogs =',blogs

  # Find blog by URL
  request = blogs.getByUrl(url=args.url)
  if debug: print 'blogs.getByUrl(url=args.url) =',request.to_json()
  response = request.execute()
  if debug: print 'response =',json.dumps(response, indent=2)
  #response = blogs.getByUrl(url=args.url).execute()

  # Get blogId
  blogId = response['id']
  if debug: print 'blogId =',blogId
  body['blog'] = {'id': blogId}

  # Post post
  posts = service.posts()
  if debug: print 'posts =',posts
  request = posts.insert(blogId=blogId, body=body, isDraft=True)
  if debug: print 'posts().insert() =',request.to_json()
  response = request.execute()
  #response = service.posts().list(blogId=blogId).execute()
  if debug: print 'response =',json.dumps(response, indent=2)


def authenticate(args, debug=False):
  """
  Handles authentication.

  Returns service object, Http object.
  """

  # Create storage for credentials
  storage = Storage('.blogger.credentials')
  if debug: print 'storage =',storage

  # Set up a Flow object to be used for authentication
  client_secrets = os.path.join(os.path.dirname(__file__),'client_secrets.json')
  flow = client.flow_from_clientsecrets(client_secrets,
      scope='https://www.googleapis.com/auth/blogger',
      message='Could not find a valid client_secrets.json file!')
  if debug: print 'flow =',flow

  # Load credentials from Storage object, or run(flow)
  credentials = storage.get() # Returns None if no credentials found
  if debug: print 'credentials =',credentials
  if credentials is None or credentials.invalid:
    credentials = run_flow(flow, storage, flags=args)
    if debug: print '2:credentials =',credentials

  # Create an httplib2.Http object to handle our HTTP requests, and authorize it
  # using the credentials.authorize() function.
  http = httplib2.Http()
  http = credentials.authorize(http)
  if debug: print 'http =',http

  # Create a service object
  service = build('blogger', 'v3', http=http)
  if debug: print 'service =',service

  return service, http


# Invoke the top-level procedure
if __name__ == '__main__': main()
